"""Read / write a value in a running Unity IL2CPP game (PS4/PS5) by a path that starts at a static field.

    python il2live.py <dumpdir> "GameStateManager::_instance._mainCharacterEntity.componentCache{611004928}.manas[0]._currentManaStatObject.baseValue"
    python il2live.py <dumpdir> "<path>" --host 192.168.0.10            # live read (ps4debug)
    python il2live.py <dumpdir> "<path>" --host 192.168.0.10 --set 999  # live write
    python il2live.py <dumpdir> --find mana                              # paths from all static fields whose field name contains "mana"
    python il2live.py <dumpdir> --find 50.0 --depth 4                    # ... whose value is 50.0

<dumpdir> holds dump.bin + dump.json (ps4dump.py) and sdk/dump.cs from Il2CppDumper (il2mem.py builds the sdk from the
same dump). Without --host every read comes from the dump. Live, the dump only provides layouts and the offset of the
TypeInfo table in the module: static roots and object classes are resolved in the running process, so the dump may come
from an earlier session of the same game build.

Path syntax (talixme's GUI passes it through unchanged):
    Class::field        static field of Class (root), nested classes as Outer.Inner, namespace optional: Ns.Class::field
    .field              instance field, base class fields included
    [i]                 element i of an array or List<T>
    {key}               Dictionary<K,V> value for key (int or string key)
    :Class              downcast (normally automatic: the object's real class is read from its klass pointer)

Layout facts (measured on PS4/PS5 dumps, metadata v29/v31, x64):
    object header 0x10 (klass*, monitor*), dump.cs class field offsets include it, struct offsets do not
    Il2CppClass: name 0x10, namespace 0x18, declaringType 0x50, parent 0x58, static_fields 0xB8
    Il2CppArray: bounds 0x10, max_length 0x18, elements from 0x20; List<T>: _items 0x10, _size 0x18
    Dictionary<K,V>: _entries 0x18, _count 0x20; Entry = {int hashCode, int next, K key @8, V value @0x10}, 0x18 bytes
    String: length 0x10, UTF-16 chars from 0x14
    dump.cs gives 0x0 for every field of an open generic class, hence the fixed tables above
"""
import argparse, json, mmap, os, re, struct, sys
import numpy as np

HEADER = 0x10
KLASS_NAME, KLASS_NS, KLASS_DECLARING, KLASS_PARENT, KLASS_STATICS = 0x10, 0x18, 0x50, 0x58, 0xB8
PRIM = dict(bool=("?", 1), sbyte=("b", 1), byte=("B", 1), short=("h", 2), ushort=("H", 2), int=("i", 4), uint=("I", 4),
            long=("q", 8), ulong=("Q", 8), float=("f", 4), double=("d", 8), char=("H", 2), IntPtr=("Q", 8), UIntPtr=("Q", 8))
MODS = {"public", "private", "internal", "protected", "static", "readonly", "const", "volatile", "abstract", "sealed", "new", "unsafe"}
TYPE_RE = re.compile(r"^(?P<mods>(?:\w+\s+)*?)(?P<kind>class|struct|enum|interface)\s+(?P<name>[^\s<]+(?:<[^>]*>)?)(?:\s*:\s*(?P<bases>.*?))?\s*// TypeDefIndex: (?P<idx>\d+)")
IMAGE_RE = re.compile(r"^// Image \d+: (?P<name>\S+) - (?P<start>\d+)")
FIELD_RE = re.compile(r"^\t(?P<decl>.+?)(?: = (?P<val>.*?))?; // 0x(?P<off>[0-9A-Fa-f]+)$")
METHOD_RE = re.compile(r"^\t(?P<vis>public|private|protected|internal)[\w ]*? void (?P<name>\w+)\(\) \{ \}$")   # parameterless void: hook candidates


# ---- dump.cs ---------------------------------------------------------------------------------------------------
class Type:
    def __init__(self, kind, name, ns, bases, idx):
        self.kind, self.name, self.ns, self.bases, self.idx = kind, name, ns, bases, idx
        self.fields, self.statics, self.enum_base = {}, {}, "int"      # offset -> (type, name)
        self.order, self.sorder = [], []                                # (type, name) in declaration order, instance / static
        self.methods = {}                                               # parameterless void methods: name -> visibility
        self.image = ""

    @property
    def full(self):
        return f"{self.ns}.{self.name}" if self.ns else self.name


def parse_dump_cs(path):
    """-> {full name: Type}; full name = Namespace.Outer.Inner"""
    types, ns, cur, images, section = {}, "", None, [], "fields"
    for line in open(path, encoding="utf-8", errors="replace"):
        line = line.rstrip("\r\n")
        m = IMAGE_RE.match(line)
        if m:
            images.append((int(m["start"]), m["name"])); continue
        if line.startswith("// Namespace: "):
            ns = line[14:].strip(); continue
        m = TYPE_RE.match(line)
        if m:
            bases = [b.strip() for b in m["bases"].split(",")] if m["bases"] else []
            cur = Type(m["kind"], m["name"], ns, bases, int(m["idx"])); types[cur.full] = cur; section = "fields"; continue
        if cur is None:
            continue
        if line == "}":
            cur = None; continue
        if line.startswith("\t// Methods"):
            section = "methods"; continue
        if line.startswith("\t// Properties"):
            section = "properties"; continue
        if section == "methods":
            m = METHOD_RE.match(line)
            if m:
                cur.methods[m["name"]] = m["vis"]
            continue
        if section == "properties":
            continue
        m = FIELD_RE.match(line)
        if m:
            off = int(m["off"], 16)
            if off >= 0x1000000:
                continue                                    # thread statics carry marker offsets
            words = m["decl"].split(" ")
            i = 0
            while i < len(words) and words[i] in MODS:
                i += 1
            mods, typ, name = set(words[:i]), " ".join(words[i:-1]), words[-1]
            if cur.kind == "enum" and name == "value__":
                cur.enum_base = typ
            elif "static" in mods:
                cur.statics[off] = (typ, name)
                cur.sorder.append((typ, name))
            else:
                cur.fields[off] = (typ, name)
                cur.order.append((typ, name))
    images.sort()
    for t in types.values():
        for start, name in images:
            if t.idx >= start:
                t.image = name
    by_short = {}
    for t in types.values():
        by_short.setdefault(t.name.split("<")[0].split(".")[-1], []).append(t)

    def base_class(t):
        """The class t derives from (bases[0] when it is a class), same namespace first: UnityEngine.Component, not
        System.ComponentModel.Component."""
        if not t.bases or not t.bases[0]:
            return None
        b = t.bases[0]
        cands = [c for c in by_short.get(b.split("<")[0].split(".")[-1], []) if c is not t and c.kind == "class"]
        if not cands:
            return None
        arity = b.count(",") + 1 if "<" in b else 0
        fit = [c for c in cands if (c.name.count(",") + 1 if "<" in c.name else 0) == arity] or cands
        return ([c for c in fit if c.ns == t.ns] or [c for c in fit if c.ns.split(".")[0] == t.ns.split(".")[0]] or fit)[0]

    done, ends = set(), {}

    def layout(t, depth=0):
        """Offsets for an open generic (dump.cs prints 0x0 for all its fields), laid out after the fields of its base
        class: BehaviourMachine<T> : MonoBehaviour starts at 0x18, behind UnityEngine.Object.m_CachedPtr, not at 0x10."""
        if id(t) in done or depth > 32:
            return
        done.add(id(t))
        base = t.name.split("<")[0]
        if base in GENERIC_LAYOUT and t.fields and all(o == 0 for o in t.fields):
            t.fields = dict(GENERIC_LAYOUT[base])
        elif "<" in t.name:
            if t.fields and (len(t.fields) > 1 or 0 in t.fields) and all(o == 0 for o in t.fields):
                t.fields = generic_layout(t.order, 0 if t.kind == "struct" else end_of(base_class(t), depth + 1))
            if len(t.statics) > 1 and all(o == 0 for o in t.statics):
                t.statics = generic_layout(t.sorder, 0)

    def end_of(t, depth=0):
        """First free offset behind the instance fields of class t and its bases (0x10 = bare object header)."""
        if t is None or depth > 32:
            return 0x10
        if id(t) in ends:
            return ends[id(t)]
        layout(t, depth)
        if t.fields:
            o = max(t.fields)
            typ = t.fields[o][0]
            st = types.get(typ) or next((c for c in by_short.get(typ.split("<")[0].split(".")[-1], []) if c.kind in ("struct", "enum")), None)
            if typ in PRIM:
                size = PRIM[typ][1]
            elif st is not None and st.kind == "struct" and st.fields:
                lt = st.fields[max(st.fields)][0]
                size = max(st.fields) + (PRIM[lt][1] if lt in PRIM else 8)
            elif st is not None and st.kind == "enum":
                size = PRIM.get(getattr(st, "enum_base", "int"), ("i", 4))[1]
            else:
                size = 8
            r = o + size
        else:
            r = end_of(base_class(t), depth + 1)
        ends[id(t)] = r
        return r

    for t in list(types.values()):                  # open generics have no offsets in dump.cs: measured layouts
        layout(t)
    return types


def generic_layout(order, off):
    """Sequential il2cpp layout for the fields of an open generic class/struct (SyncValue<T> { T _Value; Action<T>
    OnValueChanged; }): declaration order from `off` (0x10 for class instances, 0 for structs and static blocks),
    natural alignment, a type parameter counts as 8 bytes. Right for parameters that are pointers or <= 8 bytes
    (float, int, double), wrong for struct parameters."""
    out = {}
    for typ, name in order:
        size = PRIM[typ][1] if typ in PRIM else 8     # parameter, pointer, enum (int-sized, but 8 keeps the pointers aligned)
        off = (off + size - 1) & ~(size - 1)
        out[off] = (typ, name)
        off += size
    return out


GENERIC_LAYOUT = {
    "List": {0x10: ("T[]", "_items"), 0x18: ("int", "_size"), 0x1C: ("int", "_version")},
    "Dictionary": {0x10: ("int[]", "_buckets"), 0x18: ("Entry[]", "_entries"), 0x20: ("int", "_count"), 0x24: ("int", "_freeList"),
                   0x28: ("int", "_freeCount"), 0x2C: ("int", "_version")},
    "HashSet": {0x10: ("int[]", "_buckets"), 0x18: ("Slot[]", "_slots"), 0x20: ("int", "_count")},
    "Stack": {0x10: ("T[]", "_array"), 0x18: ("int", "_size"), 0x1C: ("int", "_version")},
    "Queue": {0x10: ("T[]", "_array"), 0x18: ("int", "_head"), 0x1C: ("int", "_tail"), 0x20: ("int", "_size")},
}


def split_generic(t):
    """'Dictionary<int, Component>' -> ('Dictionary', ['int', 'Component']); nested generics stay intact."""
    if "<" not in t:
        return t, []
    base, rest = t[:t.index("<")], t[t.index("<") + 1:-1]
    args, depth, cur = [], 0, ""
    for ch in rest:
        if ch == "<": depth += 1
        if ch == ">": depth -= 1
        if ch == "," and depth == 0:
            args.append(cur.strip()); cur = ""
        else:
            cur += ch
    args.append(cur.strip())
    return base, args


# ---- memory dump --------------------------------------------------------------------------------------------------
class Dump:
    def __init__(self, d, json_name="dump.json"):
        info = json.load(open(os.path.join(d, json_name)))
        self.regs = sorted(info["regions"], key=lambda r: r["start"])
        self.path = os.path.join(d, json_name.replace(".json", ".bin"))
        self.fh = open(self.path, "rb")
        self.m = mmap.mmap(self.fh.fileno(), 0, access=mmap.ACCESS_READ)
        self.starts = np.array([r["start"] for r in self.regs]); self.ends = np.array([r["end"] for r in self.regs])
        self.offs = np.array([r["offset"] for r in self.regs])
        self.pid, self.title = info.get("pid"), info.get("title_id")

    def off(self, va):
        i = np.searchsorted(self.starts, va, side="right") - 1
        if i >= 0 and va < self.ends[i]:
            return int(self.offs[i] + va - self.starts[i])
        return None

    def read(self, va, n):
        o = self.off(va)
        return self.m[o:o + n] if o is not None else None

    def u64(self, va):
        b = self.read(va, 8)
        return struct.unpack("<Q", b)[0] if b else None

    def cstr(self, va, n=96):
        b = self.read(va, n)
        return b.split(b"\0")[0].decode("latin-1") if b else None

    def module_base(self, name):
        return min(r["start"] for r in self.regs if r["name"] == name)

    def arrays(self, min_size=32):
        for r in self.regs:
            size = r["end"] - r["start"]
            if size >= min_size:
                yield r, np.frombuffer(self.m, dtype=np.uint64, count=size // 8, offset=r["offset"])


# ---- Il2Cpp runtime structures in the dump -------------------------------------------------------------------------
class Runtime:
    def __init__(self, dump, types, module="Il2CppUserAssemblies.prx"):
        self.d, self.types = dump, types
        self.dict_classes = {}                                      # (read source, dict addr) -> {':Class': count of values}
        self._name_cache = {}                                       # runtime class name -> dump.cs Type
        m = dump.m
        i = m.find(b"\xaf\x1b\xb1\xfa")
        while not (16 <= struct.unpack_from("<I", m, i + 4)[0] <= 64 and i % 16 == 0):
            i = m.find(b"\xaf\x1b\xb1\xfa", i + 4)
        r = [x for x in dump.regs if x["offset"] <= i < x["offset"] + x["end"] - x["start"]][0]
        self.meta = r["start"] + i - r["offset"]
        hdr = [struct.unpack_from("<ii", m, i + 8 + k * 8) for k in range(31)]
        self.str0, self.str1 = self.meta + hdr[2][0], self.meta + hdr[2][0] + hdr[2][1]
        td_off, td_size = hdr[19]
        self.td_off, self.td_count = td_off, td_size // 0x58
        self.typedef_names = {t.idx: t.full for t in types.values()}
        self.module = module
        self.base = dump.module_base(module)
        self._type_cache = {}
        cache = dump.path + ".klasses.json"            # the two numpy passes take ~50 s on a 3 GB dump
        try:
            c = json.load(open(cache))
            assert c["size"] == os.path.getsize(dump.path)
            self.klasses = {int(k): v for k, v in c["klasses"].items()}
            self.table_off = c["table_off"]
            self.meta_off = c["meta_off"]
        except Exception:
            name_vas = {self.str0 + struct.unpack_from("<i", m, i + td_off + k * 0x58)[0] for k in range(td_size // 0x58)}
            self.klasses = self.find_klasses(np.array(sorted(name_vas), dtype=np.uint64))
            self.by_full = {}
            for k in self.klasses:
                self.by_full.setdefault(self.full_name(k), []).append(k)
            self.table_off = self.find_table_off()
            self.meta_off = self.find_pointer_off(self.meta)
            json.dump({"size": os.path.getsize(dump.path), "klasses": self.klasses, "table_off": self.table_off, "meta_off": self.meta_off}, open(cache, "w"))
        self.klass_arr = np.array(sorted(self.klasses), dtype=np.uint64)
        self.by_full = {}
        for k in self.klasses:
            self.by_full.setdefault(self.full_name(k), []).append(k)

    def find_pointer_off(self, target):
        """Module offset of a qword holding `target` (e.g. the s_GlobalMetadata global); None if absent."""
        for r, a in self.d.arrays():
            if r["name"] == self.module:
                for j in np.nonzero(a == np.uint64(target))[0]:
                    return r["start"] + int(j) * 8 - self.base
        return None

    async def typedef_of_type(self, read, il2cpptype):
        """dump.cs full name for an Il2CppType* of a class/struct: data points at its Il2CppTypeDefinition inside the
        metadata (v27+), metadata base read live from the module global."""
        if self.meta_off is None:
            return None
        meta = await read_u64(read, self.base + self.meta_off)
        data = await read_u64(read, il2cpptype)
        idx, rest = divmod(data - meta - self.td_off, 0x58)
        return self.typedef_names.get(idx) if rest == 0 and 0 <= idx < self.td_count else None

    def find_table_off(self):
        """Module offset of the il2cpp global that points at the Il2CppClass* table indexed by TypeDefIndex
        (MetadataCache s_TypeInfoDefinitionTable). Session independent, so live roots never depend on dump addresses."""
        d = self.d
        probes = [(t.idx, self.by_full[t.full][0]) for t in self.types.values() if t.kind == "class" and t.full in self.by_full and len(self.by_full[t.full]) == 1][:40]
        if len(probes) < 5:
            return None
        i0, k0 = probes[0]
        for r, a in d.arrays():
            for idx in np.nonzero(a == np.uint64(k0))[0]:
                table = r["start"] + int(idx) * 8 - 8 * i0
                if all(d.u64(table + 8 * i) == k for i, k in probes[1:]):
                    for r2, a2 in d.arrays():
                        if r2["name"] == self.module:
                            for j in np.nonzero(a2 == np.uint64(table))[0]:
                                return r2["start"] + int(j) * 8 - self.base
        return None

    def find_klasses(self, name_arr):
        """pass 1: name/namespace point into the metadata string table; pass 2: same image pointer as pass 1 classes
        (arrays and generic instances carry runtime built names on the heap)."""
        d, out = self.d, {}
        for r, a in d.arrays():
            for idx in np.nonzero(np.isin(a, name_arr))[0]:
                if idx >= 2 and idx + 1 < len(a) and self.str0 <= int(a[idx + 1]) < self.str1:
                    out[r["start"] + int(idx) * 8 - KLASS_NAME] = d.cstr(int(a[idx]))
        images = {}
        for k in out:
            images[d.u64(k)] = images.get(d.u64(k), 0) + 1
        image_arr = np.array([i for i, c in images.items() if c >= 50], dtype=np.uint64)
        for r, a in d.arrays():
            for idx in np.nonzero(np.isin(a, image_arr))[0]:
                k = r["start"] + int(idx) * 8
                if k in out or idx + 3 >= len(a) or not (self.str0 <= int(a[idx + 3]) < self.str1):
                    continue
                s = d.cstr(int(a[idx + 2]))
                if s and 1 < len(s) < 200 and s.isprintable():
                    out[k] = s
        return out

    def full_name(self, k):
        """Namespace.Outer.Inner like dump.cs; array / generic instance names stay as the runtime built them."""
        name = self.klasses[k]
        decl = self.d.u64(k + KLASS_DECLARING)
        if decl and decl in self.klasses:
            return f"{self.full_name(decl)}.{name}"
        ns = self.d.cstr(self.d.u64(k + KLASS_NS)) or ""
        return f"{ns}.{name}" if ns else name

    def klass_of(self, full):
        ks = self.by_full.get(full)
        if not ks:
            short = full.split(".")[-1]
            ks = [k for f, l in self.by_full.items() if f.endswith("." + short) or f == short for k in l]
        if not ks:
            return None
        if len(ks) > 1:
            print(f"warning: {len(ks)} runtime classes named {full}, using the first", file=sys.stderr)
        return ks[0]

    def type_of_klass(self, k):
        """dump.cs Type for a runtime class (generic instances map to their open definition). Cached: called per object."""
        if k in self._type_cache:
            return self._type_cache[k]
        t = self.type_of_name(self.full_name(k))
        self._type_cache[k] = t
        return t

    def type_of_name(self, full):
        """dump.cs Type for a runtime class name (Entitas.Context`1 -> Entitas.Context<TEntity>, same generic arity preferred)."""
        if full in self._name_cache:
            return self._name_cache[full]
        t = self.types.get(full)
        if t is None:
            short = full.split(".")[-1]
            base = split_generic(short)[0].split("`")[0]      # runtime names generic instances Dictionary`2, dump.cs Dictionary<TKey, TValue>
            if not hasattr(self, "_by_base"):
                self._by_base = {}
                for x in self.types.values():
                    self._by_base.setdefault(x.name.split("<")[0], []).append(x)
            cands = self._by_base.get(base) or [x for x in self.types.values() if x.name == short]
            arity = int(short.split("`")[1]) if "`" in short and short.split("`")[1].isdigit() else 0
            fit = [x for x in cands if len(split_generic(x.name)[1]) == arity]     # Context`1 -> Context<TEntity>, not SimpleCollator.Context
            t = (fit or cands)[0] if cands else None
        self._name_cache[full] = t
        return t

    def object_type(self, obj):
        k = self.d.u64(obj)
        return self.type_of_klass(k) if k in self.klasses else None

    async def full_name_live(self, read, k, depth=0):
        """Namespace.Outer.Inner of a runtime class read through `read` (works live, where klass addresses differ from the dump)."""
        name = await read_cstr(read, await read_u64(read, k + KLASS_NAME))
        decl = await read_u64(read, k + KLASS_DECLARING)
        if decl and depth < 8:
            try:
                return f"{await self.full_name_live(read, decl, depth + 1)}.{name}"
            except LookupError:
                pass
        ns = await read_cstr(read, await read_u64(read, k + KLASS_NS))
        return f"{ns}.{name}" if ns else name

    async def object_type_live(self, read, obj):
        try:
            k = await read_u64(read, obj)
            full = await self.full_name_live(read, k)
        except LookupError:
            return None
        return self.type_of_name(full)

    async def statics_live(self, read, base, t, hops=0):
        """Static field block of dump.cs type t in the running process: [[base + table_off] + 8 * TypeDefIndex] -> klass
        -> static_fields. hops > 0: the block of the hops-th base class instead, via klass.parent (that is how the statics
        of a generic base like MonoSingleton<Player> are reached: generic instances are not in the TypeInfo table)."""
        if self.table_off is None:
            sys.exit("TypeInfo table not found in the dump, cannot resolve static roots")
        table = await read_u64(read, base + self.table_off)
        klass = await read_u64(read, table + 8 * t.idx)
        for _ in range(hops):
            klass = klass and await read_u64(read, klass + KLASS_PARENT)
        if not klass:
            return None, None
        return await read_u64(read, klass + KLASS_STATICS), klass


# ---- path resolution -------------------------------------------------------------------------------------------------
class Resolver:
    def __init__(self, rt):
        self.rt, self.types = rt, rt.types
        self.by_base = {}                 # 'Dictionary' -> types named Dictionary<...>, 'Inner' -> Outer.Inner types, ...
        for f, t in self.types.items():
            self.by_base.setdefault(t.name.split("<")[0], []).append(t)
            if "." in f:
                for i in range(f.count(".")):            # Ns.Outer.Inner is also reachable as Outer.Inner and Inner
                    self.by_base.setdefault(f.split(".", i + 1)[-1].split("<")[0], []).append(t)
        self.cache = {}

    def find_types(self, name):
        """Candidates for a (short or full) type name, same generic arity first: Context<GameEntity> -> Entitas.Context<TEntity>
        before SimpleCollator.Context."""
        base, args = split_generic(name)
        seen, out = set(), []
        for t in (self.types.get(name), self.types.get(base), *self.by_base.get(base, [])):
            if t is not None and id(t) not in seen:
                seen.add(id(t)); out.append(t)
        return sorted(out, key=lambda t: len(split_generic(t.name)[1]) != len(args))

    def find_type(self, name, hint_ns=""):
        key = (name, hint_ns)
        if key in self.cache:
            return self.cache[key]
        t = self.types.get(name) or (self.types.get(f"{hint_ns}.{name}") if hint_ns else None)
        if t is None:
            cands = self.find_types(name)
            arity = len(split_generic(name)[1])
            fit = [c for c in cands if len(split_generic(c.name)[1]) == arity]      # Context<GameEntity> -> Context<TEntity>, not SimpleCollator.Context
            same = [c for c in fit if c.ns == hint_ns]
            t = (same or fit or cands)[0] if cands else None
        self.cache[key] = t
        return t

    def chain(self, t):
        """t and its base classes, cycle safe (a base name can resolve back to the class itself)."""
        seen = set()
        while t is not None and id(t) not in seen and len(seen) < 64:
            seen.add(id(t))
            yield t
            t = self.find_type(t.bases[0], t.ns) if t.bases and t.bases[0] else None

    def static_field(self, t, name):
        """(parent hops, offset, type string, owner Type) of a static field of t or of a base class: hops = how many
        klass.parent steps lead to the class that owns the block. A generic base's T is substituted (MonoSingleton<Player>)."""
        declared = t.name
        for hops, c in enumerate(self.chain(t)):
            for off, (ft, fn) in c.statics.items():
                if fn == name:
                    return hops, off, self.subst(declared, c, ft), c
            declared = c.bases[0] if c.bases else ""
        return None

    @staticmethod
    def subst(declared, t, ft):
        """Field type ft of generic definition t (SyncValue<T>) with the arguments of the declared use (SyncValue<float>)."""
        params, args = split_generic(t.name)[1], split_generic(declared)[1]
        if not params or len(params) != len(args):
            return ft
        m = dict(zip(params, args))
        return re.sub(r"\b\w+\b", lambda x: m.get(x.group(0), x.group(0)), ft)

    def inherited_statics(self, t):
        """[(hops, owner Type)] for generic base classes of t that have static fields (their blocks exist per instantiation,
        so they are only reachable through t: Player::<Instance>k__BackingField for Player : MonoSingleton<Player>)."""
        return [(hops, c) for hops, c in enumerate(self.chain(t)) if hops and c.statics and "<" in c.name]

    def field(self, t, name):
        """(offset, type string, owner Type) walking base classes."""
        for c in self.chain(t):
            for off, (ft, fn) in c.fields.items():
                if fn == name:
                    return off, ft, c
        return None

    def tokens(self, path):
        head, sep, rest = path.partition("::")
        if not sep:
            sys.exit("path must start at a static field: Class::field...")
        # split on "." only outside [] / {} so keys like {Type=A.B.C} survive
        parts, buf, depth = [], "", 0
        for ch in rest:
            if ch in "[{":
                depth += 1
            elif ch in "]}":
                depth = max(0, depth - 1)
            if ch == "." and depth == 0:
                parts.append(buf)
                buf = ""
            else:
                buf += ch
        parts.append(buf)
        first = parts[0]
        segs = [("static", head, first.split("[")[0].split("{")[0])]
        tail = first[len(segs[0][2]):]
        for s in [tail] + parts[1:]:
            m = re.match(r"^([A-Za-z_<>,`0-9 ]*)((?:\[[^\]]*\]|\{[^}]*\}|:[A-Za-z_.0-9]+)*)$", s)
            if not m:
                sys.exit(f"cannot parse path segment '{s}'")
            if m.group(1):
                segs.append(("field", m.group(1)))
            for x in re.findall(r"\[[^\]]*\]|\{[^}]*\}|:[A-Za-z_.0-9]+", m.group(2)):
                segs.append(("index", x[1:-1]) if x[0] == "[" else ("key", x[1:-1]) if x[0] == "{" else ("cast", x[1:]))
        return segs


def elem_size(res, tname):
    if tname in PRIM:
        return PRIM[tname][1]
    t = res.find_type(tname)
    if t and t.kind == "enum":
        return PRIM.get(t.enum_base, ("i", 4))[1]
    if t and t.kind == "struct" and t.fields:
        return (max(t.fields) + elem_size(res, t.fields[max(t.fields)][0]) + 7) & ~7
    return 8


async def follow(res, rt, read, base, path, auto_cast=True, trace=None):
    """Resolve the path; returns (address of the final field, type string). read(va, n) -> bytes or None,
    base = module base in the process being read (dump or live)."""
    segs = res.tokens(path)
    kind, cls_name, sname = segs[0]
    t = res.find_type(cls_name)
    if not t:
        sys.exit(f"class {cls_name} not in dump.cs")
    hit = res.static_field(t, sname)
    if not hit:
        sys.exit(f"{t.full} has no static field {sname}; statics: {[fn for c in res.chain(t) for _, (_, fn) in c.statics.items()]}")
    hops, off, ftype, owner = hit
    statics, k = await rt.statics_live(read, base, t, hops)
    if not k:
        sys.exit(f"{t.full} is not initialized in the process yet")
    if not statics:
        sys.exit(f"{owner.full} has no static field block")
    addr = statics + off
    if trace is not None:
        trace.append(f"{t.full}::{sname} @ {addr:#x} ({ftype}) klass {k:#x}" + (f" ({owner.full}, {hops} parent hops)" if hops else ""))
    cur_t = None                                     # type of the object we are inside, once dereferenced
    for op, arg in segs[1:]:
        if op == "cast":
            cur_t = res.find_type(arg) or sys.exit(f"class {arg} not found")
            continue
        # dereference the value at addr to get the object we are about to enter
        if op in ("field", "index", "key"):
            base, gargs = split_generic(ftype)
            is_struct_inline = cur_t is not None and ftype not in PRIM and (ct := res.find_type(ftype, cur_t.ns)) and ct.kind == "struct" and not ftype.endswith("[]")
            if op == "field" and is_struct_inline:
                obj, cur_t = addr, ct                   # value type inline: no pointer hop
            else:
                obj = await read_u64(read, addr)
                if not obj:
                    return None, f"null at {addr:#x}"
                if op == "field":
                    cur_t = (await rt.object_type_live(read, obj) if auto_cast else None) or res.find_type(ftype, cur_t.ns if cur_t else "")
                    if cur_t is None:
                        sys.exit(f"unknown class for field type {ftype}")
            if op == "field":
                f = res.field(cur_t, arg)
                if not f:
                    sys.exit(f"{cur_t.full} has no field {arg}; fields: {[fn for _, (_, fn) in cur_t.fields.items()][:30]}")
                off, ft, owner = f
                ftype = res.subst(ftype, owner, ft)      # T of a generic instance -> the declared argument
                addr = obj + off
                if trace is not None:
                    trace.append(f".{arg} @ {addr:#x} ({ftype}) in {cur_t.full}")
                continue
            if op == "index":
                i = int(arg, 0)
                if base == "List":
                    size = struct.unpack("<i", await read_(read, obj + 0x18, 4))[0]
                    obj = await read_u64(read, obj + 0x10)
                    etype = gargs[0]
                else:
                    etype = ftype[:-2] if ftype.endswith("[]") else ftype
                    size = struct.unpack("<i", await read_(read, obj + 0x18, 4))[0]
                if i >= size:
                    return None, f"index {i} >= length {size}"
                es = elem_size(res, etype)
                addr, ftype = obj + 0x20 + i * es, etype
                if trace is not None:
                    trace.append(f"[{i}] @ {addr:#x} ({etype}, {size} elements)")
                continue
            if op == "key" and base == "HashSet":
                n = 0
                async for e in set_slots(read, obj):
                    if (arg.startswith("#") and n == int(arg[1:])) or (arg.startswith(":") and await value_class(res, rt, read, e - 8) == arg):
                        break
                    n += 1
                else:
                    return None, f"element {arg} not in set"
                addr, ftype = e + 8, gargs[0]
                if trace is not None:
                    trace.append(f"{{{arg}}} @ {addr:#x} ({ftype}, set element {n})")
                continue
            if op == "key":
                ktype, vtype = gargs[0], gargs[1]
                entries = await read_u64(read, obj + 0x18)
                count = struct.unpack("<i", await read_(read, obj + 0x20, 4))[0]
                found = None
                for n in range(count):
                    e = entries + 0x20 + n * 0x18
                    if arg.startswith("#"):
                        if n == int(arg[1:]):
                            found = e; break
                    elif arg.startswith(":"):                   # {:Class}: the entry whose value object is of that class
                        if await value_class(res, rt, read, e) == arg:
                            found = e; break
                    elif arg in await dict_key_names(res, rt, read, ktype, e):
                        found = e; break
                if found is None:
                    return None, f"key {arg} not in dictionary ({count} entries)"
                addr, ftype = found + 0x10, vtype
                if trace is not None:
                    trace.append(f"{{{arg}}} @ {addr:#x} ({vtype}, entry {n} of {count})")
    return addr, ftype


KEY_ID_FIELDS = ("_guid", "guid", "_id", "id", "_name", "name", "key", "_key", "Id", "ID", "Name")


async def set_slots(read, hs):
    """Used slots of a HashSet<T> (address of each 0x10-byte slot: int hashCode, int next, T value @ +8; free slots have hashCode < 0)."""
    slots = await read_u64(read, hs + 0x18)
    n = struct.unpack("<i", await read_(read, slots + 0x18, 4))[0] if slots else 0
    for i in range(min(n, 1 << 20)):
        e = slots + 0x20 + i * 0x10
        if struct.unpack("<i", await read_(read, e, 4))[0] >= 0:
            yield e


async def set_elem_names(res, rt, read, hs, slot):
    """Names of a HashSet element at `slot`: ':Class' first when that class is unique in the set, then '#n' (n-th used slot)."""
    n, classes, mine = 0, {}, None
    async for e in set_slots(read, hs):
        c = await value_class(res, rt, read, e - 8)
        classes[c] = classes.get(c, 0) + 1
        if e == slot:
            mine = (n, c)
        n += 1
    if mine is None:
        return []
    n, c = mine
    return ([c] if c and classes[c] == 1 else []) + [f"#{n}"]


async def value_class(res, rt, read, entry):
    """':Class' of the value object of a Dictionary entry (None for null / value types). Short name when unique in dump.cs."""
    try:
        vobj = await read_u64(read, entry + 0x10)
        t = await rt.object_type_live(read, vobj) if vobj else None
    except LookupError:
        return None
    if not t or t.kind != "class":
        return None
    return ":" + (t.name if len(res.find_types(t.name)) == 1 else t.full)


async def dict_key_names(res, rt, read, ktype, entry, vtype=None, d=None):
    """Ways to name the key of a Dictionary entry: int keys -> ['42'], string keys -> ['text'], object keys ->
    ['_guid=abc', 'name=xyz', ...] from identifier-like string/int fields of the key object (first one is used for output).
    With vtype/d (the dictionary object): int keys of a Dictionary<int, SomeClass> also get ':Class' of the value object,
    first when that class is unique in the dictionary (int keys of such type caches are hash codes that change per session)."""
    if ktype == "string":
        return [await read_string(read, await read_u64(read, entry + 8))]
    kinds = {t.kind for t in res.find_types(ktype)}
    if ktype in PRIM or kinds == {"enum"}:
        fmt = PRIM.get(ktype) or PRIM.get(res.find_types(ktype)[0].enum_base, ("i", 4))
        names = [str(struct.unpack("<" + fmt[0], await read_(read, entry + 8, fmt[1]))[0])]
        if vtype and d and vtype not in PRIM and (cls := await value_class(res, rt, read, entry)):
            key = (id(read), d)
            if key not in rt.dict_classes:                      # ponytail: one scan per dictionary, cached for --find / il2diff
                entries = await read_u64(read, d + 0x18)
                count = struct.unpack("<i", await read_(read, d + 0x20, 4))[0]
                seen = {}
                for n in range(count):
                    c = await value_class(res, rt, read, entries + 0x20 + n * 0x18)
                    seen[c] = seen.get(c, 0) + 1
                rt.dict_classes[key] = seen
            names = [cls] + names if rt.dict_classes[key].get(cls) == 1 else names + [cls]
        return names
    kobj = await read_u64(read, entry + 8)
    if not kobj:
        return []
    kt = await rt.object_type_live(read, kobj) or res.find_type(ktype)
    if kt and kt.ns == "System" and kt.name in ("Type", "RuntimeType", "MonoType"):   # System.Type key: name of the type it stands for
        try:
            name = await rt.typedef_of_type(read, await read_u64(read, kobj + 0x10))
        except LookupError:
            name = None
        return [f"Type={name}", f"Type={name.split('.')[-1]}"] if name else []
    out = []
    for c in res.chain(kt):
        for off, (ft, fn) in c.fields.items():
            if fn in KEY_ID_FIELDS and ft in ("string", "int", "uint", "long"):
                try:
                    if ft == "string":
                        v = await read_string(read, await read_u64(read, kobj + off))
                    else:
                        v = str(struct.unpack("<" + PRIM[ft][0], await read_(read, kobj + off, PRIM[ft][1]))[0])
                    out.append(f"{fn}={v}")
                except LookupError:
                    pass
    return out


async def read_string(read, sp):
    """Il2CppString: length at 0x10, UTF-16 from 0x14."""
    if not sp:
        return ""
    ln = struct.unpack("<i", await read_(read, sp + 0x10, 4))[0]
    return (await read_(read, sp + 0x14, ln * 2)).decode("utf-16-le", "replace") if 0 <= ln < 4096 else ""


async def read_(read, va, n):
    b = await read(va, n)
    if b is None or len(b) < n:
        raise LookupError(f"cannot read {n} bytes at {va:#x}")
    return b


async def read_u64(read, va):
    return struct.unpack("<Q", await read_(read, va, 8))[0]


async def read_cstr(read, va, n=96):
    b = await read(va, n) if va else None
    if not b:
        raise LookupError(f"cannot read string at {va:#x}")
    return b.split(b"\0")[0].decode("latin-1")


def value_format(res, ftype):
    if ftype in PRIM:
        return PRIM[ftype][0]
    ts = res.find_types(ftype)
    if ts and all(t.kind == "enum" for t in ts):     # a short name shared by an enum and a class (Type) is a pointer
        return PRIM.get(ts[0].enum_base, ("i", 4))[0]
    return "Q"                                       # pointers / unknown: raw qword


async def read_value(res, read, addr, ftype):
    fmt = value_format(res, ftype)
    raw = await read_(read, addr, struct.calcsize(fmt))
    v = struct.unpack("<" + fmt, raw)[0]
    return f"{v:#x}" if fmt == "Q" else v


# ---- --find: BFS from every static field ------------------------------------------------------------------------------
async def find(res, rt, read, base, word, depth, max_paths=1000, types=None, objects=False):
    """Paths from static roots to fields whose name contains `word` or whose value equals it. Prints path<TAB>type<TAB>value.
    types: only fields of these type names (int, float, ...); objects: also list matching object fields with class and address."""
    try:
        want_val = float(word)
    except ValueError:
        want_val = None
    out, seen = [], {}                               # field address -> did the path to it already contain the word
    roots = []
    for t in res.types.values():
        if t.kind != "class" or "<" in t.name:
            continue
        for hops, c in ([(0, t)] if t.statics else []) + res.inherited_statics(t):
            try:
                statics, k = await rt.statics_live(read, base, t, hops)
            except LookupError:
                continue
            if statics:
                for off, (ft, fn) in c.statics.items():
                    roots.append((f"{t.full}::{fn}", statics + off, ft, 0))
    frontier = roots
    for level in range(depth + 1):
        nxt = []
        for path, addr, ftype, _ in frontier:
            await match(res, rt, read, path, addr, ftype, word, want_val, out, types, objects)
            if level == depth:
                continue
            for child in await children(res, rt, read, path, addr, ftype):
                named = want_val is None and any(word_in(word, sg) for sg in re.sub(r"\[[^\]]*\]", "", child[0]).replace("::", ".").split(".")[1:])
                sk = (child[1], child[2])                                  # address + type: Vector3 v and v.x share an address
                if sk not in seen or (named and not seen[sk]):             # an object reached again through a path that
                    seen[sk] = named; nxt.append(child)                      # carries the word is walked once more (MainActor.*)
        frontier = nxt
        if not frontier:
            break
    for _, line in sorted(out, key=lambda h: (h[0], h[1].count(".")))[:max_paths]:   # word in the field name first, then
        print(line)                                                                  # in its parent, ... ; shallow paths first
    if len(out) > max_paths:
        print(f"# {len(out) - max_paths} more hits not shown, use a more specific word", file=sys.stderr)


TOKEN_RE = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+")
_word_cache = {}


def word_in(word, seg):
    """The search word equals one or several consecutive camelCase / snake_case tokens of the segment: "mana" matches
    manaRegen, SpellManaCurrent and {:ManaCaster} but not SettingsManager; "mainactor" matches MainActor, "hp" matches _HpValue.
    With * the word is a wildcard pattern that starts at a token: "heal*" matches currentHealth and healAmount (not
    reheal), "*health" also matches playerHealth, "max*hp" matches maxHp and MaxBaseHP.
    Memoized: --find asks this millions of times for a few thousand distinct segments."""
    key = (word, seg)
    hit = _word_cache.get(key)
    if hit is None:
        toks = [t.lower() for t in TOKEN_RE.findall(seg)]
        w = word.lower()
        if "*" in w:                                 # wildcard: "heal*" -> health, healAmount, HealthBar; "*hp" -> maxHp, currentHP
            rx = re.compile("".join(".*" if c == "*" else re.escape(c) for c in w) + r"\Z")   # still anchored at a token start
            hit = any(rx.match("".join(toks[i:])) for i in range(len(toks)))
        else:
            hit = any(w == "".join(toks[i:j]) for i in range(len(toks)) for j in range(i + 1, min(i + 5, len(toks) + 1)))
        _word_cache[key] = hit
    return hit


async def match(res, rt, read, path, addr, ftype, word, want_val, out, types=None, objects=False):
    """Hit if the word is in any path segment after the root class (field names, object names, dictionary keys: both
    MainActor._ActorModel.HP._Value and CurrentStats{Type=SpellManaCurrent}.baseValue match "mana"/"mainactor"), or if the
    value equals the number given. Numbers/bools are listed with their value, an object field that matches by name
    with its class and address."""
    fmt = value_format(res, ftype)
    if (fmt == "Q" and not objects) or (types and ftype not in types):
        return
    if fmt == "Q" and ftype not in PRIM and (st := res.find_type(ftype)) is not None and st.kind == "struct":
        return                                       # inline struct: its own fields (.x .y .z) are the hits, not a "pointer"
    try:
        v = struct.unpack("<" + fmt, await read_(read, addr, struct.calcsize(fmt)))[0]
    except LookupError:
        return
    segs = re.sub(r"\[[^\]]*\]", "", path).replace("::", ".").split(".")[1:]     # [1:]: GameStateManager must not match "mana"
    if want_val is not None:
        if fmt != "Q" and v == want_val:
            out.append((0, f"{path}	{ftype}	{v}"))
        return
    where = [i for i, sg in enumerate(reversed(segs)) if word_in(word, sg)]       # 0 = field name, 1 = its parent, ...
    if not where:
        return
    if fmt != "Q":
        out.append((where[0], f"{path}	{ftype}	{v}"))
    elif where[0] == 0 and v:                                                      # the object itself: class and address
        t = await rt.object_type_live(read, v)
        out.append((0, f"{path}	{t.full if t else ftype}	{v:#x}"))


async def children(res, rt, read, path, addr, ftype):
    """Objects reachable from the field at addr: pointer fields -> their fields; arrays/lists -> elements (first 16)."""
    if ftype in PRIM:
        return []
    base, gargs = split_generic(ftype)
    if not ftype.endswith("[]") and (st := res.find_type(ftype)) is not None and st.kind == "struct":
        # value type stored inline (Vector3 maxVelocity, Color, custom structs): its fields follow at addr, no pointer hop;
        # struct offsets in dump.cs carry no object header. UnityEngine structs are walked too (Vector3.x etc.)
        if rt.d.off(addr) is None:
            return []
        return [(f"{path}.{fn}", addr + off, res.subst(ftype, st, ft), 0) for off, (ft, fn) in st.fields.items()]
    try:
        obj = await read_u64(read, addr)
    except LookupError:
        return []
    if not obj or rt.d.off(obj) is None:
        return []
    out = []
    if ftype.endswith("[]") or base == "List":
        etype = gargs[0] if base == "List" else ftype[:-2]
        try:
            if base == "List":
                obj = await read_u64(read, obj + 0x10)
                if not obj:
                    return []
            size = struct.unpack("<i", await read_(read, obj + 0x18, 4))[0]
        except LookupError:        # stale / garbage pointer in a field that is typed as a list: nothing to walk
            return []
        es = elem_size(res, etype)
        ref = etype not in PRIM and not (res.find_type(etype) or Type("class", "", "", [], 0)).kind in ("struct", "enum")
        for i in range(min(size, 4096)):                     # sparse reference arrays (Entitas _components[410]): skip nulls
            a = obj + 0x20 + i * es
            if ref:
                try:
                    if not await read_u64(read, a):
                        continue
                except LookupError:
                    break
            out.append((f"{path}[{i}]", a, etype, 0))
            if len(out) >= 256:
                break
        return out
    if base == "HashSet":
        try:
            elems = []
            async for e in set_slots(read, obj):
                if len(elems) >= 256:
                    break
                elems.append((e, await value_class(res, rt, read, e - 8)))
            counts = {}
            for _, c in elems:
                counts[c] = counts.get(c, 0) + 1
            for n, (e, c) in enumerate(elems):             # {:Class} only when that class is unique in the set, else {#n}
                out.append((f"{path}{{{c if c and counts[c] == 1 else '#%d' % n}}}", e + 8, gargs[0], 0))
        except LookupError:
            pass
        return out
    if base == "Dictionary":
        ktype, vtype = gargs
        try:
            entries = await read_u64(read, obj + 0x18)
            count = struct.unpack("<i", await read_(read, obj + 0x20, 4))[0]
            for n in range(min(count, 256)):
                e = entries + 0x20 + n * 0x18
                if not await read_u64(read, e + 0x10):
                    continue
                names = await dict_key_names(res, rt, read, ktype, e, vtype, obj)
                out.append((f"{path}{{{names[0] if names else '#%d' % n}}}", e + 0x10, vtype, 0))
        except LookupError:
            pass
        return out
    t = await rt.object_type_live(read, obj) or res.find_type(ftype)
    if not t or t.kind not in ("class", "struct") or t.ns.startswith(("System", "UnityEngine", "TMPro", "Unity.")):
        return []
    for c in res.chain(t):
        for off, (ft, fn) in c.fields.items():
            out.append((f"{path}.{fn}", obj + off, res.subst(ftype, c, ft), 0))
    return out


# ---- main ---------------------------------------------------------------------------------------------------------------
async def game_pid(dbg):
    """PID of the running game: eboot.bin, else the single process whose title id starts with CUSA/PPSA.
    (from ps4-unreal-dumper tools/ueobj.py)"""
    procs = await dbg.get_processes()
    c = [p.pid for p in procs if p.name.rstrip("\0") == "eboot.bin"]
    if not c:
        for p in procs:
            if p.pid > 100:
                try:
                    if (await dbg.get_process_info(p.pid)).title_id.startswith(("CUSA", "PPSA")):
                        c.append(p.pid)
                except Exception:
                    pass
    if len(c) == 1:
        return c[0]
    sys.exit(f"expected one game process, found {len(c)}: {[(p.pid, p.name.rstrip(chr(0))) for p in procs if p.pid > 100]}")


async def amain(a):
    dump = Dump(a.dumpdir, a.json)
    types = parse_dump_cs(os.path.join(a.dumpdir, "sdk", "dump.cs"))
    rt = Runtime(dump, types, a.module)
    res = Resolver(rt)
    print(f"{len(types)} types, {len(rt.klasses)} runtime classes, metadata {rt.meta:#x}, TypeInfo table at {a.module}+{rt.table_off:#x}", file=sys.stderr)

    if a.host:
        import ps4debug
        dbg = ps4debug.PS4Debug(a.host)
        pid = await game_pid(dbg)
        maps = await dbg.get_process_maps(pid)            # a list of map entries (name, start, end, prot)
        bases = [e.start for e in maps if e.name.rstrip("\0") == a.module]
        if not bases:
            sys.exit(f"{a.module} not mapped in pid {pid}; is the game running?")
        base = min(bases)
        rt.base = base                                   # live module base for the TypeInfo table and metadata globals
        print(f"live: pid {pid}, {a.module} at {base:#x}", file=sys.stderr)
        async def read(va, n):
            return await dbg.read_memory(pid, va, n)
    else:
        base = rt.base
        async def read(va, n):
            return dump.read(va, n)

    if a.find:
        await find(res, rt, read, base, a.find, a.depth, types=set(a.types.split(",")) if a.types else None, objects=a.objects)
        return
    trace = []
    addr, ftype = await follow(res, rt, read, base, a.path, trace=trace)
    for line in trace:
        print("  " + line, file=sys.stderr)
    if addr is None:
        sys.exit(f"path ends early: {ftype}")
    val = await read_value(res, read, addr, ftype)
    print(f"{a.path}\t{ftype}\t{val}\t@ {addr:#x}")
    if a.fields:                                          # the fields of the object the path points to (or contains)
        obj = addr if value_format(res, ftype) != "Q" else await read_u64(read, addr)
        t = await rt.object_type_live(read, obj) if obj else None
        if not t:
            sys.exit(f"{ftype} is not an object")
        for c in res.chain(t):
            for off, (ft, fn) in sorted(c.fields.items()):
                ft = res.subst(ftype, c, ft)
                try:
                    v = await read_value(res, read, obj + off, ft)
                    if value_format(res, ft) == "Q" and int(v, 16):
                        vt = await rt.object_type_live(read, int(v, 16))
                        v = f"{v} ({vt.full})" if vt else v
                except LookupError:
                    v = "?"
                print(f"  .{fn}\t{ft}\t{v}\t@ {obj + off:#x}")
    if a.set is not None:
        if not a.host:
            sys.exit("--set needs --host (writing into a dump file makes no sense)")
        fmt = value_format(res, ftype)
        new = float(a.set) if fmt in "fd" else int(a.set, 0) if fmt != "?" else a.set.lower() in ("1", "true")
        await dbg.write_memory(pid, addr, struct.pack("<" + fmt, new))
        print(f"written, now: {await read_value(res, read, addr, ftype)}")


if __name__ == "__main__":
    import asyncio
    ap = argparse.ArgumentParser()
    ap.add_argument("dumpdir")
    ap.add_argument("path", nargs="?")
    ap.add_argument("--json", default="dump.json", help="dump json name inside dumpdir (default dump.json)")
    ap.add_argument("--host", help="PS4/PS5 IP for live access via ps4debug (default: read from the dump)")
    ap.add_argument("--module", default="Il2CppUserAssemblies.prx", help="il2cpp module name (default Il2CppUserAssemblies.prx)")
    ap.add_argument("--set", help="value to write (live only)")
    ap.add_argument("--find", help="field name substring or numeric value to search from all static fields")
    ap.add_argument("--depth", type=int, default=7, help="pointer hops for --find (default 7, a few seconds on a dump)")
    ap.add_argument("--types", help="--find: only fields of these types, comma separated (e.g. int,float,double)")
    ap.add_argument("--objects", action="store_true", help="--find: also list matching object fields with class and address")
    ap.add_argument("--fields", action="store_true", help="path: also list every field of the object the path points to, with values")
    a = ap.parse_args()
    if not a.path and not a.find:
        ap.error("path or --find required")
    asyncio.run(amain(a))
