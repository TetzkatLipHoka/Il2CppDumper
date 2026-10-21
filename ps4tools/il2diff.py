"""Compare two memory dumps of the same game session and turn the changed values into il2live paths.

    python il2diff.py <dumpdir> dump_mana_50.json dump_mana_77.json --eq 50 77
    python il2diff.py <dumpdir> a.json b.json --eq 50 77 --depth 10 --paths 3
    python il2diff.py <dumpdir> before.json after.json --changed [--same before2.json] [--class Marker]
        # no value needed: every int/float/bool/enum field of a game object that differs, then paths for the first hits
    python il2diff.py <dumpdir> dump.json --addr 0x203f12318 [0x...]
        # one dump, the address of the value (found with a scanner): only the backward walk to a static field

Both dumps come from ps4dump.py in ONE game session (object addresses must match), <dumpdir>/sdk/dump.cs from
Il2CppDumper. --eq A B keeps the 32-bit ints and floats that are A in the first dump and B in the second.
For every hit the owner object is found through its klass pointer, then the references to that object are followed
backwards (fields, array elements, List<T>, Dictionary<K,V> entries) until a static field block is reached.
Output per line: path<TAB>type<TAB>value in a<TAB>value in b, verified by resolving the path in both dumps.
"""
import argparse, os, struct, sys
import numpy as np
import il2live
from il2live import KLASS_STATICS, KLASS_PARENT, PRIM, split_generic

NOISE_NS = ("System", "UnityEngine", "TMPro", "Unity.", "Cinemachine")
NOISE_NAMES = ("StatChangedArgs", "Action", "Delegate", "MulticastDelegate", "Func", "EventHandler")


def as_int(v):
    try:
        return int(str(v), 0)
    except ValueError:
        return None


class Diff:
    def __init__(self, dumpdir, ja, jb, depth, max_parents):
        self.a = il2live.Dump(dumpdir, ja)
        self.b = il2live.Dump(dumpdir, jb) if jb and jb != ja else self.a
        self.types = il2live.parse_dump_cs(os.path.join(dumpdir, "sdk", "dump.cs"))
        self.rt = il2live.Runtime(self.a, self.types)
        self.res = il2live.Resolver(self.rt)
        self.depth, self.max_parents = depth, max_parents
        self._refs, self._steps = None, {}

        async def aread(va, n):
            return self.a.read(va, n)
        self.aread = aread
        self.klass_arr = self.rt.klass_arr
        # static field blocks: start -> (Type, size)
        self.statics = {}
        parents = {k: self.a.u64(k + KLASS_PARENT) for k in self.rt.klasses}
        for k, name in self.rt.klasses.items():
            sf = self.a.u64(k + KLASS_STATICS)
            t = self.rt.type_of_klass(k)
            if sf and t and t.statics:
                label = t.full
                if "`" in name:                              # generic instance (MonoSingleton`1): name the block after the class that
                    kids = [c for c, pk in parents.items() if pk == k and "`" not in self.rt.klasses[c]]   # inherits it, Player::<Instance>
                    arg = self.generic_arg(k)
                    kt = [self.rt.type_of_klass(c) for c in kids]
                    kt = [x for x in kt if x] and ([x for x in kt if x and x.full == arg] or [x for x in kt if x])
                    if kt:
                        label = kt[0].full
                self.statics[sf] = (t, max(t.statics) + 8, label)
        self.static_starts = np.array(sorted(self.statics), dtype=np.uint64)

    def generic_arg(self, k):
        """dump.cs name of the first type argument of a generic instance klass (Il2CppClass.generic_class -> context ->
        class_inst -> type_argv[0] -> typedef handle), None if it is not a class/struct."""
        try:
            gc = self.a.u64(k + 0x60)
            inst = gc and self.a.u64(gc + 8)
            argv = inst and self.a.u64(inst + 8)
            tp = argv and self.a.u64(argv)
            data = tp and self.a.u64(tp)
            meta = self.a.u64(self.rt.base + self.rt.meta_off)
            idx, rest = divmod(data - meta - self.rt.td_off, 0x58)
            return self.rt.typedef_names.get(idx) if rest == 0 else None
        except (TypeError, struct.error):
            return None

    # ---- value scan ---------------------------------------------------------------------------------------------------
    def scan(self, va, vb):
        """Addresses whose 32-bit int or float is va in dump a and vb in dump b. Regions are matched by address overlap,
        region boundaries move between dumps when the heap grows."""
        hits = []
        for r in self.a.regs:
            for rb in self.b.regs:
                lo, hi = max(r["start"], rb["start"]), min(r["end"], rb["end"])
                if hi - lo < 4:
                    continue
                n = (hi - lo) // 4
                oa, ob = r["offset"] + lo - r["start"], rb["offset"] + lo - rb["start"]
                for dtype, fa, fb in ((np.int32, as_int(va), as_int(vb)), (np.float32, float(va), float(vb))):
                    if fa is None or fb is None:
                        continue                       # 2.5 is never an int32
                    x = np.frombuffer(self.a.m, dtype=dtype, count=n, offset=oa)
                    y = np.frombuffer(self.b.m, dtype=dtype, count=n, offset=ob)
                    for i in np.nonzero((x == fa) & (y == fb))[0]:
                        hits.append((lo + int(i) * 4, "int" if dtype is np.int32 else "float"))
        return sorted(set(hits))

    # ---- object structure ---------------------------------------------------------------------------------------------
    def index(self):
        """Sorted index of every qword in the dump that points into a dumped region (tens of millions; one pass, a few
        seconds), plus the sorted addresses of the qwords that are Il2CppClass pointers, i.e. object starts."""
        if self._refs is None:
            d = self.a
            vals, addrs = [], []
            for r, a in d.arrays():
                i = np.searchsorted(d.starts, a, side="right") - 1
                ok = (i >= 0) & (a < d.ends[np.maximum(i, 0)])
                idx = np.nonzero(ok)[0]
                vals.append(a[idx]); addrs.append(r["start"] + idx.astype(np.uint64) * 8)
            vals, addrs = np.concatenate(vals), np.concatenate(addrs)
            order = np.argsort(vals, kind="stable")
            vals, addrs = vals[order], addrs[order]
            self._refs = (vals, addrs, np.sort(addrs[np.isin(vals, self.klass_arr)]))
        return self._refs

    def owner(self, va, maxback=0x100000):
        """(object start, klass) of the object containing va: nearest preceding qword that is an Il2CppClass pointer."""
        d = self.a
        if d.off(va) is None:
            return None
        starts = self.index()[2]
        i = np.searchsorted(starts, np.uint64(va), side="right") - 1
        if i < 0:
            return None
        start = int(starts[i])
        if va - start > maxback or np.searchsorted(d.starts, va, side="right") != np.searchsorted(d.starts, start, side="right"):
            return None                                      # too far back or in another region
        return start, d.u64(start)

    def refs(self, target):
        """Addresses of every qword equal to target: binary search in the pointer index."""
        vals, addrs, _ = self.index()
        lo, hi = np.searchsorted(vals, np.uint64(target), side="left"), np.searchsorted(vals, np.uint64(target), side="right")
        return [int(x) for x in addrs[lo:hi]]

    def static_root(self, va):
        i = np.searchsorted(self.static_starts, va, side="right") - 1
        if i < 0:
            return None
        start = int(self.static_starts[i])
        t, size, label = self.statics[start]
        if va >= start + size:
            return None
        off = va - start
        name = next((fn for o, (_, fn) in t.statics.items() if o == off), None)
        return f"{label}::{name}" if name else None

    def field_name(self, t, off):
        for c in self.res.chain(t):
            if off in c.fields:
                return c.fields[off][1], c.fields[off][0]
        return None, None

    async def step_up(self, va):
        """What holds the pointer/value at va: ('static', path) | ('obj', object start, suffix piece) | None.
        Dictionary entries and List buffers are collapsed into {key} / [i] on the owning container. Cached per address."""
        if va not in self._steps:
            self._steps[va] = await self._step_up(va)
        return self._steps[va]

    async def _step_up(self, va):
        root = self.static_root(va)
        if root:
            return ("static", root)
        ow = self.owner(va)
        if not ow:
            return None
        start, k = ow
        name = self.rt.klasses.get(k, "")
        if name.endswith("[]"):                                  # Il2CppArray, elements from 0x20
            elem = name[:-2]
            length = self.a.u64(start + 0x18) or 0
            if elem == "Slot":                                   # HashSet<T>.Slot[]: {hash, next, value@8}, 0x10 bytes
                i, rest = divmod(va - start - 0x20, 0x10)
                if rest != 8 or i >= length:
                    return None
                sets = [r for r in self.refs(start) if (o := self.owner(r)) and r - o[0] == 0x18]
                if not sets:
                    return None
                hs = self.owner(sets[0])[0]
                names = await il2live.set_elem_names(self.res, self.rt, self.aread, hs, va - 8)
                return ("obj", hs, f"{{{names[0]}}}") if names else None
            if elem == "Entry":                                  # Dictionary<K,V>.Entry[]: {hash, next, key@8, value@0x10}
                i, rest = divmod(va - start - 0x20, 0x18)
                if rest != 0x10 or i >= length:
                    return None
                dicts = [r for r in self.refs(start) if (o := self.owner(r)) and r - o[0] == 0x18]
                if not dicts:
                    return None
                d = self.owner(dicts[0])[0]
                kt = self.rt.type_of_klass(self.a.u64(d))
                if kt and kt.name.startswith("Dictionary"):
                    ktype, vtype = self.dict_key_type(d)
                    names = await il2live.dict_key_names(self.res, self.rt, self.aread, ktype, start + 0x20 + i * 0x18, vtype, d)
                    return ("obj", d, f"{{{names[0] if names else '#%d' % i}}}")
                return None
            es = il2live.elem_size(self.res, elem)
            i, rest = divmod(va - start - 0x20, es)
            if i >= length:
                return None
            piece = f"[{i}]"
            if rest:
                t = self.res.find_type(elem)
                fn, _ = self.field_name(t, rest) if t else (None, None)
                if not fn:
                    return None
                piece += f".{fn}"
            lists = [r for r in self.refs(start) if (o := self.owner(r)) and r - o[0] == 0x10]
            for r in lists:                                      # List<T>._items -> report on the List object
                lst = self.owner(r)[0]
                lt = self.rt.type_of_klass(self.a.u64(lst))
                if lt and lt.name.startswith("List"):
                    return ("obj", lst, piece)
            return ("obj", start, piece)
        t = self.rt.type_of_klass(k)
        if not t:
            return None
        fn, _ = self.field_name(t, va - start)
        if not fn:
            return None
        return ("obj", start, f".{fn}")

    def dict_key_type(self, d):
        """(key type, value type) of a Dictionary object: whoever points at it tells us its declared field type."""
        for r in self.refs(d):
            ow = self.owner(r)
            if ow:
                t = self.rt.type_of_klass(ow[1])
                if t:
                    _, ft = self.field_name(t, r - ow[0])
                    if ft and ft.startswith("Dictionary<"):
                        return tuple(split_generic(ft)[1][:2])
        return "int", None

    async def paths_to(self, va, max_paths):
        """Static-rooted paths that reach the value at va, shortest first."""
        done, out = [], []
        frontier = [(va, "")]
        seen = set()
        for level in range(self.depth):
            nxt = []
            for addr, suffix in frontier:
                s = await self.step_up(addr)
                if not s:
                    continue
                if s[0] == "static":
                    out.append(s[1] + suffix)
                    if len(out) >= max_paths:
                        return out
                    continue
                _, obj, piece = s
                if obj in seen:
                    continue
                seen.add(obj)
                t = self.rt.type_of_klass(self.a.u64(obj))
                if t and (t.ns.startswith(NOISE_NS) and not t.name.startswith(("List", "Dictionary", "Entry", "HashSet", "Slot")) or t.name in NOISE_NAMES):
                    continue
                kept = 0                                     # only references that lead somewhere count against --parents:
                for r in self.refs(obj):                     # MethodInfo/anon-region refs and unmapped generic owners are noise
                    if kept >= self.max_parents:
                        break
                    if await self.step_up(r) is None:
                        continue
                    nxt.append((r, piece + suffix)); kept += 1
            frontier = nxt
            if not frontier:
                break
        return out

    async def chain(self, va):
        """Owner chain of va along the first reference each (for a hit without static root): ['Player.health', 'List<Player>[2]', ...]."""
        out, seen = [], set()
        for _ in range(self.depth):
            s = await self.step_up(va)
            if not s:
                break
            if s[0] == "static":
                out.append(s[1]); break
            _, obj, piece = s
            t = self.rt.type_of_klass(self.a.u64(obj))
            out.append(f"{t.full if t else '?'}{piece} @ {obj:#x}")
            seen.add(obj)
            for va in self.refs(obj):                       # first reference that steps up to an object not seen yet (delegates point back)
                up = await self.step_up(va)
                if up is not None and (up[0] == "static" or up[1] not in seen):
                    break
            else:
                out.append("(no usable reference to this object)"); break
        return out

    # ---- --changed: every scalar field of game objects that differs between the dumps ------------------------------------
    def changed(self, images, cls_filter, same=None):
        """[(address, 'Class.field', type, value a, value b)] for scalar fields of objects whose class lives in one of
        `images` (dump.cs image names, substring match). `same` = third dump in which the value must equal dump a
        (a second dump of the unchanged state filters timers, positions and other constantly moving values).
        Per region: changed 32-bit words via numpy, then only fields that lie on a changed word are decoded."""
        game = {}
        for k, name in self.rt.klasses.items():
            if name.endswith("[]"):
                continue
            t = self.rt.type_of_klass(k)
            if t and t.kind == "class" and any(i.lower() in t.image.lower() for i in images) and (not cls_filter or cls_filter.lower() in t.full.lower()):
                game[k] = t
        karr = np.array(sorted(game), dtype=np.uint64)
        layouts = {}
        for t in game.values():
            if t.full in layouts:
                continue
            fields = []
            for c in self.res.chain(t):
                for off, (ft, fn) in c.fields.items():
                    fmt = il2live.value_format(self.res, ft)
                    if fmt != "Q":
                        fields.append((off, fn, ft, fmt))
            layouts[t.full] = fields
        out, objects = [], 0
        for r, a in self.a.arrays():
            rb = [x for x in self.b.regs if x["start"] <= r["start"] < x["end"]]
            if not rb:
                continue
            rb = rb[0]
            hi = min(r["end"], rb["end"])
            n = (hi - r["start"]) // 4
            x = np.frombuffer(self.a.m, dtype=np.uint32, count=n, offset=r["offset"])
            y = np.frombuffer(self.b.m, dtype=np.uint32, count=n, offset=rb["offset"] + r["start"] - rb["start"])
            changed = np.flatnonzero(x != y)
            if len(changed) == 0:
                continue
            changed_words = set(changed.tolist()) if len(changed) < 1 << 20 else None
            for idx in np.nonzero(np.isin(a, karr))[0]:
                obj = r["start"] + int(idx) * 8
                t = game[int(a[idx])]
                objects += 1
                for off, fn, ft, fmt in layouts[t.full]:
                    w = (obj + off - r["start"]) // 4
                    if w >= n or (changed_words is not None and w not in changed_words) or (changed_words is None and x[w] == y[w]):
                        continue
                    size = struct.calcsize(fmt)
                    ba, bb = self.a.read(obj + off, size), self.b.read(obj + off, size)
                    if ba is None or bb is None or ba == bb:
                        continue
                    if same is not None and same.read(obj + off, size) != ba:
                        continue
                    out.append((obj + off, f"{t.full}.{fn}", ft, struct.unpack("<" + fmt, ba)[0], struct.unpack("<" + fmt, bb)[0]))
        print(f"{objects} objects of {len(game)} game classes compared, {len(out)} scalar fields differ", file=sys.stderr)
        return out

    async def verify(self, path):
        vals = []
        for d in (self.a, self.b):
            async def read(va, n, d=d):
                return d.read(va, n)
            try:
                addr, ftype = await il2live.follow(self.res, self.rt, read, self.rt.base, path)
                if addr is None:
                    return None
                vals.append((await il2live.read_value(self.res, read, addr, ftype), ftype))
            except SystemExit:
                return None
        return vals


async def amain(a):
    diff = Diff(a.dumpdir, a.a, a.b, a.depth, a.parents)
    if a.addr:
        for va in a.addr:
            va = int(va, 0)
            paths = await diff.paths_to(va, a.paths)
            for p in paths:
                v = await diff.verify(p)
                print(f"{p}	{v[0][1]}	{v[0][0]}" if v else f"# {p}: does not resolve")
            if not paths:
                print(f"# {va:#x}: no static root within {a.depth} hops; owner chain: " + " <- ".join(await diff.chain(va)), file=sys.stderr)
        return
    if a.changed:
        same = il2live.Dump(a.dumpdir, a.same) if a.same else None
        rows = diff.changed(a.images.split(","), a.cls, same)
        for addr, name, ft, va, vb in rows:
            print(f"{name}	{ft}	{va}	{vb}	@ {addr:#x}")
        for addr, name, ft, va, vb in rows[:a.hits]:
            for p in await diff.paths_to(addr, a.paths):
                v = await diff.verify(p)
                if v:
                    print(f"{p}	{v[0][1]}	{v[0][0]}	{v[1][0]}")
        return
    hits = diff.scan(a.eq[0], a.eq[1])
    shared = sum(min(r["end"], rb["end"]) - max(r["start"], rb["start"]) for r in diff.a.regs for rb in diff.b.regs if min(r["end"], rb["end"]) > max(r["start"], rb["start"]))
    print(f"{len(hits)} locations are {a.eq[0]} in {a.a} and {a.eq[1]} in {a.b} ({shared >> 20} MB compared)", file=sys.stderr)
    for va, kind in hits[:a.hits]:
        paths = await diff.paths_to(va, a.paths)
        if not paths:
            print(f"# {va:#x} ({kind}): no static root within {a.depth} hops; owner chain: " + " <- ".join(await diff.chain(va)), file=sys.stderr)
        for p in paths:
            v = await diff.verify(p)
            if v:
                print(f"{p}\t{v[0][1]}\t{v[0][0]}\t{v[1][0]}")
            else:
                print(f"# {p}: does not resolve", file=sys.stderr)


if __name__ == "__main__":
    import asyncio
    ap = argparse.ArgumentParser()
    ap.add_argument("dumpdir")
    ap.add_argument("a", help="first dump json (e.g. dump_mana_50.json)")
    ap.add_argument("b", nargs="?", help="second dump json (not needed with --addr)")
    ap.add_argument("--addr", nargs="+", help="address(es) of the value in the first dump: backward walk only, no scan")
    ap.add_argument("--eq", nargs=2, metavar=("A", "B"), help="value in the first and in the second dump")
    ap.add_argument("--changed", action="store_true", help="list every scalar field of game objects that differs between the dumps")
    ap.add_argument("--same", help="third dump json in which the value must still equal the first dump (filters moving values)")
    ap.add_argument("--images", default="Assembly-CSharp", help="comma separated image name substrings for --changed (default Assembly-CSharp)")
    ap.add_argument("--class", dest="cls", help="only classes whose name contains this (for --changed)")
    ap.add_argument("--depth", type=int, default=10, help="reference hops from the value to a static field (default 10)")
    ap.add_argument("--paths", type=int, default=3, help="paths to report per hit (default 3)")
    ap.add_argument("--parents", type=int, default=6, help="references followed per object (default 6)")
    ap.add_argument("--hits", type=int, default=20, help="hits to trace (default 20)")
    args = ap.parse_args()
    if not args.eq and not args.changed and not args.addr:
        ap.error("--eq A B, --changed or --addr required")
    if (args.eq or args.changed) and not args.b:
        ap.error("--eq / --changed need two dumps")
    asyncio.run(amain(args))
