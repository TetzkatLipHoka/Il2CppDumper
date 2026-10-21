"""Generate a TLH trainer (cheat menu / Phoenix Studio import) from il2live paths of a Unity IL2CPP game (PS4/PS5).

    python il2cheat.py <dumpdir> out.TLH "Mana=GameStateManager::_instance._mainCharacterEntity.componentCache{611004928}.manas[0]._currentManaStatObject.baseValue=999" ...
    python il2cheat.py <dumpdir> out.TLH --hook PlayerLifeBar "Name=path=value" ...
    python il2cheat.py <dumpdir> --check "path"           # emulate the generated hops against the dump, compare with il2live

Each cheat is "Name=path=value": the path is il2live syntax (Class::static, .field, [i], {key}, {Type=X}, :Cast), the value
is written every frame while the cheat is on (int/float/bool/byte/short/long/enum fields). The hook is the first byte of
an Update() method of a game class that has a live instance in the dump (--hook picks the class), the cave resolves
every path from the static root on every call: no addresses from the dump survive into the trainer except module
offsets (TypeInfo table, metadata pointer, hook AOB), so it works across sessions and restarts.

Register use in the cave: rax = current slot address, rcx/rdx = dictionary walk, r8/r9 = Type key compare
(all saved around the cheat blocks). Flag/Val cells are TLH GetMem cells like uecheat. Symbols are loaded with movabs:
older keystone builds encode `mov rax, 0x854F3C10` as a sign-extended imm32 (0xFFFFFFFF854F3C10), movabs forces imm64.
Dictionary hops: int keys, {Type=X} keys and {:Class} keys (value object of that class) are matched at runtime; an int
key of a Dictionary<int, SomeClass> becomes {:Class} when the class is unique in the dictionary, because such type
caches use per-session hash codes as keys. String/_guid keys fall back to the entry index seen in the dump
(ponytail: the entry order of a Dictionary only changes on remove, documented in the comment).
"""
import json, os, re, struct, sys
import numpy as np
import il2live
from il2live import KLASS_STATICS, KLASS_PARENT, PRIM, split_generic, elem_size

MODULE = "Il2CppUserAssemblies.prx"
HOOK_METHODS = ("Update", "LateUpdate", "FixedUpdate", "OnUpdate", "OnLateUpdate", "OnFixedUpdate", "Tick", "OnTick",
                "CustomUpdate", "OnCustomUpdate", "UpdateLogic", "DoUpdate", "ManualUpdate")   # per-frame methods, preferred first
CELL = dict(float=("Single", 4, "edx", "<f"), double=("Double", 8, "rdx", "<d"), int=("Integer", 4, "edx", "<i"), uint=("Cardinal", 4, "edx", "<I"),
            long=("Int64", 8, "rdx", "<q"), ulong=("UInt64", 8, "rdx", "<Q"), short=("SmallInt", 2, "dx", "<h"), ushort=("Word", 2, "dx", "<H"),
            byte=("Byte", 1, "dl", "<B"), sbyte=("ShortInt", 1, "dl", "<b"), bool=("Boolean", 1, "dl", "<B"))


# ---- path -> hops ---------------------------------------------------------------------------------------------------
# hop kinds: ("root", Type, static offset, field type, parent hops) | ("deref",) | ("add", off) | ("index", i, elemsize, is_list)
#            | ("key_int", value) | ("key_type", TypeDefIndex, name) | ("key_class", TypeDefIndex, name) | ("key_nth", n, key text)
#            the final slot is the value
async def compile_path(res, rt, read, base, path):
    """Path -> hops. Object classes behind pointers are read from the dump (auto downcast like il2live), string/_guid
    dictionary keys are resolved to their entry index in the dump."""
    segs = res.tokens(path)
    _, cls_name, sname = segs[0]
    t = res.find_type(cls_name) or sys.exit(f"class {cls_name} not in dump.cs")
    hit = res.static_field(t, sname) or sys.exit(f"{t.full} has no static field {sname}")
    hops, ftype, cur_t = [("root", t, hit[1], hit[2], hit[0])], hit[2], None
    for op, arg in segs[1:]:
        if op == "cast":
            cur_t = res.find_type(arg) or sys.exit(f"class {arg} not found"); continue
        base_name, gargs = split_generic(ftype)
        if op == "field":
            inline = cur_t is not None and ftype not in PRIM and (ct := res.find_type(ftype, cur_t.ns)) and ct.kind == "struct" and not ftype.endswith("[]")
            if inline:
                cur_t = ct
            else:
                hops.append(("deref",))
                obj = await emulate(rt, read, base, hops)
                cur_t = (await rt.object_type_live(read, obj) if obj else None) or res.find_type(ftype, cur_t.ns if cur_t else "")
                if cur_t is None:
                    sys.exit(f"unknown class for field type {ftype}")
            f = res.field(cur_t, arg) or sys.exit(f"{cur_t.full} has no field {arg}")
            off, ft, owner = f
            ftype = res.subst(ftype, owner, ft)
            if off:
                hops.append(("add", off))
        elif op == "index":
            i = int(arg, 0)
            etype = gargs[0] if base_name == "List" else ftype[:-2]
            hops += [("deref",), ("index", i, elem_size(res, etype), base_name == "List")]
            ftype = etype
        elif op == "key":
            hops.append(("deref",))
            if base_name == "HashSet":
                if arg.startswith("#"):
                    hops.append(("set_nth", int(arg[1:])))
                elif arg.startswith(":"):
                    ct = res.find_type(arg[1:]) or sys.exit(f"{arg}: class {arg[1:]} not in dump.cs")
                    hops.append(("set_class", ct.idx, ct.full))
                else:
                    sys.exit(f"{arg}: a HashSet element is addressed as {{#n}} or {{:Class}}")
                ftype = gargs[0]
                continue
            ktype, vtype = gargs
            if arg.startswith("#"):
                hops.append(("key_nth", int(arg[1:]), arg))
            elif arg.startswith("Type="):
                kt = res.find_type(arg[5:]) or sys.exit(f"{arg}: type {arg[5:]} not in dump.cs")
                hops.append(("key_type", kt.idx, kt.full))
            elif arg.startswith(":"):                           # entry whose value object is of that class
                ct = res.find_type(arg[1:]) or sys.exit(f"{arg}: class {arg[1:]} not in dump.cs")
                hops.append(("key_class", ct.idx, ct.full))
            elif ktype in PRIM or (ktype != "string" and res.find_types(ktype) and all(x.kind == "enum" for x in res.find_types(ktype))):
                hops.append(("key_int", int(arg, 0)))
                if vtype not in PRIM:                           # int keys of a type cache are per-session hash codes: match the value's class instead
                    d = await emulate(rt, read, base, hops[:-1])
                    e = d and await emulate(rt, read, base, hops)
                    names = e and await il2live.dict_key_names(res, rt, read, ktype, e - 0x10, vtype, d)
                    if names and names[0].startswith(":"):
                        ct = res.find_type(names[0][1:])
                        hops[-1] = ("key_class", ct.idx, ct.full)
                        print(f"  {{{arg}}} -> {{{names[0]}}} (int key is a per-session hash, the value's class is unique in the dictionary)")
            else:                                               # string / object key: entry index from the dump
                d = await emulate(rt, read, base, hops) or sys.exit(f"{arg}: dictionary is null in the dump")
                entries = await il2live.read_u64(read, d + 0x18)
                count = struct.unpack("<i", await il2live.read_(read, d + 0x20, 4))[0]
                for n in range(count):
                    if arg in await il2live.dict_key_names(res, rt, read, ktype, entries + 0x20 + n * 0x18):
                        hops.append(("key_nth", n, arg)); break
                else:
                    sys.exit(f"key {arg} not found in the dump ({count} entries)")
            ftype = vtype
    return hops, ftype


# ---- hops -> assembly -------------------------------------------------------------------------------------------------
def asm_hops(rt, hops, fail):
    code = []
    for h in hops:
        k = h[0]
        if k == "root":
            t, off = h[1], h[2]
            code += ["movabs rax, TypeInfoTable", "mov rax, [rax]", "test rax, rax", f"jz {fail}",
                     f"mov rax, [rax+{8 * t.idx:#x}]", "test rax, rax", f"jz {fail}"]                 # Il2CppClass*
            code += [f"mov rax, [rax+{KLASS_PARENT:#x}]", "test rax, rax", f"jz {fail}"] * h[4]       # statics of a (generic) base class
            code += [f"mov rax, [rax+{KLASS_STATICS:#x}]", "test rax, rax", f"jz {fail}"]             # static field block
            if off:
                code.append(f"add rax, {off:#x}")
        elif k == "deref":
            code += ["mov rax, [rax]", "test rax, rax", f"jz {fail}"]
        elif k == "add":
            code.append(f"add rax, {h[1]:#x}")
        elif k == "index":
            i, es, is_list = h[1], h[2], h[3]
            code += [f"cmp dword ptr [rax+0x18], {i}", f"jle {fail}"]                                 # _size / max_length
            if is_list:
                code += ["mov rax, [rax+0x10]", "test rax, rax", f"jz {fail}", f"cmp dword ptr [rax+0x18], {i}", f"jle {fail}"]
            code.append(f"add rax, {0x20 + i * es:#x}")
        elif k in ("set_nth", "set_class"):                  # HashSet<T>: walk the used slots (hashCode >= 0), 0x10 bytes each
            lbl = fail.replace("_end", "") + f"_s{len(code)}"
            code += ["mov rdx, [rax+0x18]", "test rdx, rdx", f"jz {fail}", "mov ecx, dword ptr [rdx+0x18]", "add rdx, 0x20"]  # slots, length
            if k == "set_nth":
                code += [f"mov r8d, {h[1]}"]
            else:
                code += ["movabs r8, TypeInfoTable", "mov r8, [r8]", "test r8, r8", f"jz {fail}", f"mov r8, [r8+{8 * h[1]:#x}]"]
            code += [f"{lbl}_loop:", "test ecx, ecx", f"jz {fail}", "cmp dword ptr [rdx], 0", f"jl {lbl}_next"]
            if k == "set_nth":
                code += ["test r8d, r8d", f"jz {lbl}_found", "dec r8d"]
            else:
                code += ["mov r9, [rdx+8]", "test r9, r9", f"jz {lbl}_next", "cmp qword ptr [r9], r8", f"je {lbl}_found"]
            code += [f"{lbl}_next:", "add rdx, 0x10", "dec ecx", f"jmp {lbl}_loop", f"{lbl}_found:", "lea rax, [rdx+8]"]
        elif k in ("key_int", "key_type", "key_class", "key_nth"):
            lbl = fail.replace("_end", "") + f"_k{len(code)}"
            code += ["mov rdx, [rax+0x18]", "test rdx, rdx", f"jz {fail}", "mov ecx, dword ptr [rax+0x20]", "add rdx, 0x20"]  # entries, count
            if k == "key_nth":
                code += [f"cmp ecx, {h[1]}", f"jle {fail}", f"lea rax, [rdx+{h[1] * 0x18 + 0x10:#x}]"]
                code.append(f"; dictionary entry #{h[1]} = key {h[2]} in the dump, key not verified at runtime")
                continue
            if k == "key_type":
                code += ["movabs r8, MetadataPtr", "mov r8, [r8]", f"add r8, {rt.td_off + h[1] * 0x58:#x}"]    # Il2CppTypeDefinition* of the key type
            if k == "key_class":
                code += ["movabs r8, TypeInfoTable", "mov r8, [r8]", "test r8, r8", f"jz {fail}", f"mov r8, [r8+{8 * h[1]:#x}]"]   # Il2CppClass* of the value class
            code += [f"{lbl}_loop:", "test ecx, ecx", f"jz {fail}"]
            if k == "key_int":
                code += [f"cmp dword ptr [rdx+8], {h[1]}", f"je {lbl}_found"]
            elif k == "key_class":
                code += ["mov r9, [rdx+0x10]", "test r9, r9", f"jz {lbl}_next",                                # value object -> klass
                         "cmp qword ptr [r9], r8", f"je {lbl}_found", f"{lbl}_next:"]
            else:
                code += ["mov r9, [rdx+8]", "test r9, r9", f"jz {lbl}_next", "mov r9, [r9+0x10]", "test r9, r9", f"jz {lbl}_next",   # RuntimeType.type
                         "cmp qword ptr [r9], r8", f"je {lbl}_found", f"{lbl}_next:"]
            code += ["add rdx, 0x18", "dec ecx", f"jmp {lbl}_loop", f"{lbl}_found:", "lea rax, [rdx+0x10]"]
    return code


# ---- emulation of the hops against the dump (self check, the asm is not executed here) ---------------------------------
async def emulate(rt, read, base, hops):
    a = None
    for h in hops:
        k = h[0]
        if k == "root":
            table = await il2live.read_u64(read, base + rt.table_off)
            klass = await il2live.read_u64(read, table + 8 * h[1].idx)
            for _ in range(h[4]):
                klass = await il2live.read_u64(read, klass + KLASS_PARENT)
            a = await il2live.read_u64(read, klass + KLASS_STATICS) + h[2]
        elif k == "deref":
            a = await il2live.read_u64(read, a)
            if not a:
                return None
        elif k == "add":
            a += h[1]
        elif k == "index":
            i, es, is_list = h[1], h[2], h[3]
            if struct.unpack("<i", await il2live.read_(read, a + 0x18, 4))[0] <= i:
                return None
            if is_list:
                a = await il2live.read_u64(read, a + 0x10)
                if not a or struct.unpack("<i", await il2live.read_(read, a + 0x18, 4))[0] <= i:
                    return None
            a += 0x20 + i * es
        elif k in ("set_nth", "set_class"):
            want = h[1] if k == "set_nth" else await il2live.read_u64(read, await il2live.read_u64(read, base + rt.table_off) + 8 * h[1])
            n, a = 0, a
            async for e in il2live.set_slots(read, a):
                if k == "set_nth" and n == want:
                    a = e + 8; break
                if k == "set_class":
                    vobj = await il2live.read_u64(read, e + 8)
                    if vobj and await il2live.read_u64(read, vobj) == want:
                        a = e + 8; break
                n += 1
            else:
                return None
        else:
            entries = await il2live.read_u64(read, a + 0x18)
            count = struct.unpack("<i", await il2live.read_(read, a + 0x20, 4))[0]
            if k == "key_nth":
                a = entries + 0x20 + h[1] * 0x18 + 0x10 if count > h[1] else None
                continue
            meta = await il2live.read_u64(read, base + rt.meta_off) if k == "key_type" else 0
            want = meta + rt.td_off + h[1] * 0x58 if k == "key_type" else h[1]
            if k == "key_class":
                want = await il2live.read_u64(read, await il2live.read_u64(read, base + rt.table_off) + 8 * h[1])
            for n in range(count):
                e = entries + 0x20 + n * 0x18
                if k == "key_int":
                    got = struct.unpack("<i", await il2live.read_(read, e + 8, 4))[0]
                elif k == "key_class":
                    vobj = await il2live.read_u64(read, e + 0x10)
                    got = await il2live.read_u64(read, vobj) if vobj else 0
                else:
                    kobj = await il2live.read_u64(read, e + 8)
                    tp = await il2live.read_u64(read, kobj + 0x10) if kobj else 0
                    got = await il2live.read_u64(read, tp) if tp else 0
                if got == want:
                    a = e + 0x10; break
            else:
                return None
    return a


# ---- hook selection ----------------------------------------------------------------------------------------------------
def live_instances(rt, dump):
    """{klass: number of objects} over all dumped regions. An object start is a klass pointer whose next qword is the
    monitor (0 or a pointer outside the module) and whose fourth qword does not point into the metadata: that drops the
    MethodInfo (klass at +0x20, return_type at +0x28 in the module), FieldInfo (klass at +0x10, offset|token after it) and
    PropertyInfo (klass at +0, name at +0x18 in the metadata) structures; regions that hold Il2CppClass structs themselves
    (metadata pools, full of klass refs in typeHierarchy/parent/castClass) are skipped. Region names alone do not
    separate heap and pools on every platform (PS4: dlmalloc_extra, PS5 Unity 6: ScriptingGetMem, pools unnamed or dlmalloc)."""
    mods = [(r["start"], r["end"]) for r in dump.regs if (r["name"] or "").endswith((".prx", ".sprx", ".elf", "eboot.bin"))]
    meta = next((r for r in dump.regs if r["start"] <= rt.meta < r["end"]), None)
    pools = set((np.searchsorted(dump.starts, rt.klass_arr, side="right") - 1).tolist())   # regions holding Il2CppClass structs:
    counts = {}                                                                             # metadata pools, full of klass refs (typeHierarchy, parent...)
    for i, (r, a) in enumerate(dump.arrays()):
        if any(lo <= r["start"] < hi for lo, hi in mods) or r["name"] == "executable" or len(a) < 4:
            continue
        if dump.regs.index(r) in pools:
            continue
        idx = np.nonzero(np.isin(a[:-3], rt.klass_arr))[0]
        if len(idx) == 0:
            continue
        mon, fourth = a[idx + 1], a[idx + 3]
        ok = mon == 0
        for lo, hi in mods:
            ok |= (mon >= np.uint64(0x10000)) & ~((mon >= lo) & (mon < hi))
        if meta:
            ok &= ~((fourth >= meta["start"]) & (fourth < meta["end"]))
        v, c = np.unique(a[idx[ok]], return_counts=True)
        for k, n in zip(v.tolist(), c.tolist()):
            counts[k] = counts.get(k, 0) + n
    return counts


def pick_hook(rt, res, dump, script, want=None, images=("Assembly-CSharp.dll",), roots=()):
    """(method name, RVA, aob bytes, site instructions) for an Update() of a game class with live instances."""
    import capstone
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    text = [r for r in dump.regs if r["name"] == rt.module and r["prot"] & 4][0]
    blob = dump.m[text["offset"]:text["offset"] + text["end"] - text["start"]]
    counts = live_instances(rt, dump)
    for t in res.types.values():                     # an Update() of a base class runs for the instances of its subclasses too
        n = sum(counts.get(k, 0) for k in rt.by_full.get(t.full, []))
        if n:
            for c in list(res.chain(t))[1:]:
                for k in rt.by_full.get(c.full, []):
                    counts[k] = counts.get(k, 0) + n
    cands = []
    want_cls, _, want_meth = want.partition(".") if want else (None, None, None)   # --hook Class or --hook Class.Method
    for e in script["ScriptMethod"]:
        cls, _, meth = e["Name"].rpartition("$$")
        if (meth not in HOOK_METHODS and meth != want_meth) or "<" in cls:
            continue
        if want and (cls.split(".")[-1] != want_cls or (want_meth and meth != want_meth)):
            continue
        t = res.find_type(cls)
        if not t or t.image not in images:
            continue
        n = sum(counts.get(k, 0) for k in rt.by_full.get(t.full, []))
        if n:
            core = 0 if re.search(r"Manager|System|Controller|Player|Game|Hud|HUD", cls) else 1
            unity_msg = meth in ("Update", "LateUpdate", "FixedUpdate") and any(c.name == "MonoBehaviour" for c in res.chain(t))
            if unity_msg:                                     # called by the engine through the method pointer, never inlined
                weak = False
            else:                                             # custom per-frame method: a private one may be inlined into its caller
                weak = t.methods.get(meth) == "private"
            prio = HOOK_METHODS.index(meth) if meth in HOOK_METHODS else len(HOOK_METHODS)
            cands.append((n != 1, t.full not in roots, not unity_msg, weak, core, prio, n, cls, meth, e["Address"]))   # a root class of the paths first
    if want is None and os.environ.get("IL2CHEAT_LIST_HOOKS"):
        for c in sorted(cands)[:25]:
            print(f"  candidate {c[7]}.{c[8]} instances={c[6]}{'' if not c[2] else ' (custom)'}{' (private)' if c[3] else ''}", file=sys.stderr)
    for _, _, _, _, _, _, n, cls, meth, rva in sorted(cands):
        site, size = [], 0
        for ins in md.disasm(blob[rva:rva + 32], text["start"] + rva):
            if "rip" in ins.op_str or (not site and ins.mnemonic == "jmp"):    # rip-relative, or a thunk that only jumps on
                site = None; break
            site.append(f"{ins.mnemonic} {ins.op_str}".strip()); size += ins.size
            if size >= 5:
                break
        if not site:
            continue
        for length in range(16, 96, 4):
            pat = bytes(blob[rva:rva + length])
            if blob.count(pat) == 1:
                return f"{cls}.{meth}", rva, pat, site, n
    sys.exit("no usable per-frame hook (no candidate with live instances, or all start rip-relative / have no unique AOB); try --hook Class or --hook Class.Method")


def xml_escape(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


async def amain(a):
    dump = il2live.Dump(a.dumpdir, a.json)
    types = il2live.parse_dump_cs(os.path.join(a.dumpdir, "sdk", "dump.cs"))
    rt = il2live.Runtime(dump, types, a.module)
    res = il2live.Resolver(rt)
    if rt.table_off is None or rt.meta_off is None:
        sys.exit("TypeInfo table / metadata globals not found in the dump")

    async def read(va, n):
        return dump.read(va, n)

    if a.check:
        hops, ftype = await compile_path(res, rt, read, rt.base, a.check)
        emu = await emulate(rt, read, rt.base, hops)
        ref, _ = await il2live.follow(res, rt, read, rt.base, a.check)
        print("\n".join(asm_hops(rt, hops, "c1_end")))
        print(f"\nemulated {emu and hex(emu)} vs il2live {ref and hex(ref)} -> {'OK' if emu == ref else 'MISMATCH'}")
        return

    cheats, blocks, mems, images, roots = [], [], [], {"Assembly-CSharp.dll"}, set()   # game assemblies: Assembly-CSharp plus whatever the roots live in
    for k, spec in enumerate(a.specs, 1):
        name, rest = spec.split("=", 1)                  # the path itself may contain "=" ({Type=X}, {_guid=...})
        path, value = rest.rsplit("=", 1)
        hops, ftype = await compile_path(res, rt, read, rt.base, path)
        emu = await emulate(rt, read, rt.base, hops)
        ref, _ = await il2live.follow(res, rt, read, rt.base, path)
        if emu != ref:
            sys.exit(f"{name}: hop emulation {emu and hex(emu)} differs from il2live {ref and hex(ref)}, codegen bug")
        vt = ftype
        et = res.find_type(ftype)
        if ftype not in CELL and et and et.kind == "enum":
            vt = et.enum_base
        if vt not in CELL:
            sys.exit(f"{name}: field type {ftype} not supported (number/bool/enum only)")
        tlh_type, size, vreg, fmt = CELL[vt]
        mems.append(f"GetMem( Flag{k}, 1 )")
        entries = [f"      <Symbol>Flag{k}</Symbol>\n      <Type>Value</Type>\n      <ValueType>Boolean</ValueType>\n      <Value>0</Value>"]
        code = [f"cmp byte ptr [Flag{k}], 1", f"jne c{k}_end"] + asm_hops(rt, hops, f"c{k}_end")
        if vt == "bool":
            code.append(f"mov byte ptr [rax], {int(value.strip().lower() not in ('0', 'false', 'no'))}")
        else:
            mems.append(f"GetMem( Val{k}, {size} )")
            code += [f"mov {vreg}, [Val{k}]", f"mov [rax], {vreg}"]
            entries.append(f"      <Symbol>Val{k}</Symbol>\n      <Type>Value</Type>\n      <ValueType>{tlh_type}</ValueType>\n      <Value>{value}</Value>")
        blocks.append("\n".join(code + [f"c{k}_end:"]))
        cheats.append((name, entries))
        print(f"{name}: {path} ({ftype}) = {value}, {len(hops)} hops, offline slot {ref:#x}")
        images.add(hops[0][1].image); roots.add(hops[0][1].full)

    script = json.load(open(os.path.join(a.dumpdir, "sdk", "script.json")))
    hook, rva, aob, site, n = pick_hook(rt, res, dump, script, a.hook, images, roots)
    print(f"hook: {hook} at {a.module}+{rva:#x} ({n} live instance{'s' if n != 1 else ''}), AOB {len(aob)} bytes, site: {'; '.join(site)}")

    syms = [f"RegisterSymbol( TypeInfoTable, ModuleBase+{rt.table_off:#x} )", f"RegisterSymbol( MetadataPtr, ModuleBase+{rt.meta_off:#x} )"]
    asm = "\n".join(mems + syms + ["", "pushfq", "push rax", "push rcx", "push rdx", "push r8", "push r9", ""]
                    + blocks + ["", "done:", "pop r9", "pop r8", "pop rdx", "pop rcx", "pop rax", "popfq"] + site)
    info = json.load(open(os.path.join(a.dumpdir, a.json)))
    title = info.get("title_id", "")
    cusa = int(title[4:]) if title[4:].isdigit() else 0
    game = xml_escape(a.game or os.path.basename(a.out).split("_")[0])
    aob_s = "-".join(f"{b:02X}" for b in aob)
    xml = ['<?xml version="1.0" encoding="utf-8" standalone="no"?>',
           f'<Trainer xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
           f'Game="{game}" Creator="il2cheat" CUSA="{cusa}" Version="{a.version}" Process="eboot.bin" Legacy="1">',
           f'  <StartUP Name="IL2CPP hook ({xml_escape(hook)})" Description="static roots via the il2cpp TypeInfo table, resolved every frame">',
           '    <Entry>', '      <Section>0</Section>', f'      <Section-Name>{a.module}</Section-Name>', '      <Section-Protection>5</Section-Protection>', f'      <AOB>{aob_s}</AOB>',
           '      <Type>Injection</Type>', f'      <Assembly>{xml_escape(asm)}</Assembly>', '    </Entry>', '  </StartUP>']
    for name, entries in cheats:
        xml.append(f'  <Cheat Name="{xml_escape(name)}" Description="">')
        for en in entries:
            xml += ['    <Entry>', '      <Section>0</Section>', en, '    </Entry>']
        xml.append('  </Cheat>')
    xml.append('</Trainer>')
    open(a.out, "w", encoding="utf-8-sig", newline="\n").write("\n".join(xml) + "\n")
    print(f"wrote {a.out}: {len(cheats)} cheats, hook {hook}")


if __name__ == "__main__":
    import argparse, asyncio
    ap = argparse.ArgumentParser()
    ap.add_argument("dumpdir")
    ap.add_argument("out", nargs="?", help="output .TLH")
    ap.add_argument("specs", nargs="*", help='"Name=path=value"')
    ap.add_argument("--json", default="dump.json")
    ap.add_argument("--module", default=MODULE)
    ap.add_argument("--hook", help="Class or Class.Method to hook (default: an Update-like method of an Assembly-CSharp class with one live instance)")
    ap.add_argument("--game", help="game name for the TLH header (default: from the output file name)")
    ap.add_argument("--version", default="", help="game version for the TLH header, e.g. 1.00")
    ap.add_argument("--check", help="path: print the generated hops and compare the emulation with il2live")
    a = ap.parse_args()
    if not a.check and (not a.out or not a.specs):
        ap.error("out.TLH and at least one Name=path=value required (or --check path)")
    asyncio.run(amain(a))
