"""Propose item cheats for a Unity IL2CPP game from the dump: the item enum, the game's own give method and how to reach its
object, printed as ready il2cheat specs (the ReaperPy unity_items idea, without the GUI).

    python il2items.py <dumpdir>                 # best enum + give methods, 5 example specs per method
    python il2items.py <dumpdir> --all           # one spec per enum member for the best give method
    python il2items.py <dumpdir> --enum Weapons --method AddAmmo

Ranking is by name (ItemID-like enums with many members; Add/Give/Grant... methods with an enum/int id parameter and an
optional count), game assemblies only. An instance method needs an object: il2items searches the static roots (depth 4)
for one of the owner class and prints the path, or suggests hooking the owner's Update and calling this.Method(...).
Object parameters (ItemData, Ammunition) are taken from a List / array / Dictionary of such objects reachable from a static
root, the element picked by an editable cell ([$0] / {$0}); without one the method is listed with the reason and a spec template.
"""
import argparse, asyncio, os, re, struct, sys
import il2live
from il2live import PRIM

ITEM_ENUM = re.compile(r"(?i)item|inventor|loot|weapon|equip|consum|material|resource|gear|armo|ingredient|food|tool|ammo|currenc")
ITEM_ENUM_GOOD = re.compile(r"(?i)^(e)?(item|inventoryitem|lootitem)(s)?(id|ids|name|names|key|keys|type|types)?$")
ITEM_ENUM_BAD = re.compile(r"(?i)slot|rarity|quality|state|status|category|flag|event|action|sound|sfx|anim|button|tutorial|quest|"
                           r"achievement|trophy|input|keycode|layer|mode$|result|error|direction|language|platform|shader|render|texture")
SKIP_VALUE = re.compile(r"(?i)^(none|null|empty|invalid|unknown|undefined|default|count|max|min|length|size|num[a-z]*|total|last|first|end|begin|all|any|__.*)$")
GIVE = re.compile(r"(?i)^(add|give|grant|obtain|receive|pickup|pick_?up|collect|gain|acquire|award|reward|unlock|put|insert|store|try_?add)")
BAD_GIVE = re.compile(r"(?i)remove|delete|drop|use|consume|sell|buy|destroy|clear|reset|check|contains|find|event|callback|update|refresh|save|load|"
                      r"serial|sync|rpc|network|ui|display|show|text|listener|handler")
GIVE_CLASS = re.compile(r"(?i)inventor|bag|backpack|storage|chest|stash|container|pocket|loot|item|player|character|hero|wallet|equipment|data|save")
GIVE_CLASS_STRONG = re.compile(r"(?i)inventor|bag|backpack|wallet|item(?!spawner)|loot")
ID_PARAM = re.compile(r"(?i)^(id|item_?id|itemid|item|type|item_?type|kind|key|index|idx|uid|code|what|weapon|ammo)$|item|weapon|ammo")
COUNT_PARAM = re.compile(r"(?i)count|amount|num|quantity|qty|stack|number|size|value|package")
INTS = ("sbyte", "byte", "short", "ushort", "int", "uint", "long", "ulong")


def real_values(t):
    seen, out = set(), []
    for n, v in t.consts.items():
        if not SKIP_VALUE.match(n) and v not in seen:
            seen.add(v); out.append((n, v))
    return out


ENEMY = re.compile(r"(?i)enemy|monster|boss|npc|hostile")


def enum_score(t, give_types, main):
    vals = real_values(t)
    if t.kind != "enum" or len(vals) < 4 or t.image.startswith(il2live.GAME_IMAGE_SKIP):
        return 0
    s = 6 if ITEM_ENUM_GOOD.match(t.name) else 3 if ITEM_ENUM.search(t.name) else 0
    if not s and t.full not in give_types:
        return 0
    s -= 3 * (len(vals) < 12) + 5 * bool(ITEM_ENUM_BAD.search(t.name)) + 3 * bool(ENEMY.search(t.name))
    s += 3 * (t.full in give_types) + 2 * (1 if t.image in main else -1) + min(len(vals), 400) / 100 - 2 * (len(vals) > 3000)
    return s


def classify(res, m):
    """-> (id index, count index, enum Type or None) or a reason string why the method cannot be called from a trainer."""
    if "<" in m.cls.name or "<" in m.name:
        return "generic"
    args = m.args
    id_i = cnt_i = None
    for i, (pt, pn) in enumerate(args):
        if "ref " in pt or "out " in pt:
            return f"parameter {pn} is ref/out"
        et = res.find_type(pt)
        if et and et.kind == "enum" and (id_i is None or ITEM_ENUM.search(pt)):
            id_i = i
    if id_i is None:
        for i, (pt, pn) in enumerate(args):
            if pt in INTS and ID_PARAM.search(pn) and not COUNT_PARAM.search(pn):
                id_i = i; break
    if id_i is None:
        objs = [f"{pt} {pn}" for pt, pn in args if pt not in PRIM and not (res.find_type(pt) or il2live.Type("x", "", "", [], 0)).kind == "enum"]
        return f"no enum/int item id parameter ({', '.join(objs) or 'no parameters'})"
    for i, (pt, pn) in enumerate(args):
        if i != id_i and pt in INTS + ("float", "double") and COUNT_PARAM.search(pn):
            cnt_i = i; break
    if cnt_i is None:
        cnt_i = next((i for i, (pt, pn) in enumerate(args) if i != id_i and pt == "int"), None)
    for i, (pt, pn) in enumerate(args):
        if i not in (id_i, cnt_i) and pt not in PRIM and not (res.find_type(pt) or il2live.Type("x", "", "", [], 0)).kind == "enum":
            return f"parameter {pn} is a {pt} object"
    et = res.find_type(args[id_i][0])
    return id_i, cnt_i, et if et and et.kind == "enum" else None


def give_score(m, cls, enum_t, main=()):
    s = 6 if GIVE.match(m.name) else -3
    s += 2 if m.cls.image in main else -2
    s -= 6 * bool(BAD_GIVE.search(m.name)) + 2 * bool(re.match(r"(?i)^(try|can|has)", m.name))
    s += 3 * bool(GIVE_CLASS.search(m.cls.name)) + 2 * bool(GIVE_CLASS_STRONG.search(m.cls.name)) + 5 * (enum_t is not None and cls is enum_t) + 2 * (cls is not None)
    s += 1 * (m.ret in ("void", "bool")) - max(0, len(m.args) - 3)
    return s


_NODES = None


async def nodes(res, rt, read, base, depth=4):
    """Every (path, slot address, field type) within `depth` hops of a static root, BFS order (shortest paths first); walked once."""
    global _NODES
    if _NODES is not None:
        return _NODES
    frontier, seen, out = [], set(), []
    for t in res.types.values():
        if t.kind != "class" or "<" in t.name or not (t.statics or res.inherited_statics(t)):
            continue
        for hops, c in ([(0, t)] if t.statics else []) + res.inherited_statics(t):
            try:
                statics, k = await rt.statics_live(read, base, t, hops)
            except LookupError:
                continue
            if statics:
                frontier += [(f"{t.full}::{fn}", statics + off, ft) for off, (ft, fn) in c.statics.items()]
    for _ in range(depth + 1):
        nxt = []
        for path, addr, ftype in frontier:
            out.append((path, addr, ftype))
            for child in await il2live.children(res, rt, read, path, addr, ftype):
                if child[1] not in seen:
                    seen.add(child[1]); nxt.append(child[:3])
        frontier = nxt
    _NODES = out
    return out


async def object_path(res, rt, read, base, owner):
    """Shortest path from a static root to an object of class `owner` (or a subclass) in the dump, or None."""
    want = {c.full for c in res.types.values() if any(x is owner for x in res.chain(c))}
    for path, addr, ftype in await nodes(res, rt, read, base):
        if il2live.value_format(res, ftype) == "Q":
            try:
                obj = await il2live.read_u64(read, addr)
                ot = rt.object_type(obj) if obj else None
            except LookupError:
                ot = None
            if ot and ot.full in want:
                return path
    return None


async def collection_path(res, rt, read, base, elem):
    """Shortest path to a non-empty List<T> / T[] / Dictionary<int or enum, T> of `elem` objects (or subclasses) in the
    dump, with the element picked by an editable il2cheat cell: 'Root::db.items[$0]' / '{$0}', plus the element count."""
    want = {c.name for c in res.types.values() if any(x is elem for x in res.chain(c))}
    for path, addr, ftype in await nodes(res, rt, read, base):
        bn, ga = il2live.split_generic(ftype)
        if (ftype.endswith("[]") and ftype[:-2] in want) or (bn == "List" and ga and ga[0] in want):
            suffix, cnt = "[$0]", 0x18
        elif bn == "Dictionary" and len(ga) == 2 and ga[1] in want and (ga[0] in INTS or (res.find_type(ga[0]) or il2live.Type("x", "", "", [], 0)).kind == "enum"):
            suffix, cnt = "{$0}", 0x20
        else:
            continue
        try:
            obj = await il2live.read_u64(read, addr)
            n = struct.unpack("<i", await il2live.read_(read, obj + cnt, 4))[0] if obj else 0
        except LookupError:
            n = 0
        if n > 0:
            return path + suffix, n
    return None


async def amain(a):
    dump = il2live.Dump(a.dumpdir, a.json)
    types = il2live.parse_dump_cs(os.path.join(a.dumpdir, "sdk", "dump.cs"))
    rt = il2live.Runtime(dump, types, a.module)
    res = il2live.Resolver(rt)

    async def read(va, n):
        return dump.read(va, n)

    gives, rejected = [], []
    for t in res.types.values():
        if t.kind not in ("class", "struct") or t.image.startswith(il2live.GAME_IMAGE_SKIP):
            continue
        for name, ms in t.sigs.items():
            if (a.method and name != a.method) or not (GIVE.search(name) and not BAD_GIVE.search(name)) or name.startswith((".", "<", "add_", "remove_")):
                continue
            for m in ms:
                c = classify(res, m)
                if isinstance(c, str):
                    rejected.append((m, c))
                else:
                    gives.append((m,) + c)
    main = il2live.main_images(types)
    give_types = {g[3].full for g in gives if g[3]}
    enums = sorted(((enum_score(t, give_types, main), t) for t in res.types.values()), key=lambda x: -x[0])
    enums = [(s, t) for s, t in enums if s > 0]
    if a.enum:
        et = res.find_type(a.enum) or sys.exit(f"enum {a.enum} not in dump.cs")
        enums = [(99, et)] + [(s, t) for s, t in enums if t is not et]
    if not enums:
        sys.exit("no item-like enum in the game assemblies; name one with --enum")
    best = enums[0][1]
    print(f"item enums: " + ", ".join(f"{t.name} ({len(real_values(t))} members, {s:.1f})" for s, t in enums[:6]))
    gives.sort(key=lambda g: -give_score(g[0], g[3], best, main))
    rejected.sort(key=lambda r: -give_score(r[0], None, best, main))
    if not gives:
        sys.exit("no give-like method with an enum/int item parameter; rejected: " + "; ".join(f"{m.sig}: {why}" for m, why in rejected[:10]))
    async def receiver(m):
        """-> (what the call starts with: 'Class.' / 'path.' / 'this.', note) or None when the object is unreachable."""
        if m.static:
            return f"{m.cls.name}.", "static"
        path = await object_path(res, rt, read, rt.base, m.cls)
        hooks = [h for h in m.cls.methods if h in ("Update", "LateUpdate", "FixedUpdate")]
        if path:
            return f"{path}.", f"object via {path}"
        if hooks and il2live.instances_of(res, rt, dump, m.cls):
            return "this.", f"no static path; hook the owner: --hook {m.cls.name}.{hooks[0]}"
        print(f"# {m.sig}: no static path to a {m.cls.name} object and no per-frame method to hook")
        return None

    shown = 0
    for m, id_i, cnt_i, et in gives[:a.limit]:
        if a.method and m.name != a.method:
            continue
        et = et or best
        args = m.args
        r = await receiver(m)
        if not r:
            continue
        target, note = r[0] + m.name, r[1]
        members = real_values(et) if et.kind == "enum" else [(f"id{v}", v) for v in range(1, 6)]
        print(f"\n# {m.sig} RVA {m.rva:#x} [{note}], id = {args[id_i][0]} {args[id_i][1]}" + (f", count = {args[cnt_i][1]}" if cnt_i is not None else ""))
        if members:                                      # one rule for every item: the id is an editable cell (enum members = their numbers)
            vals = [f"${members[0][0]}" if i == id_i and et.kind == "enum" else f"${members[0][1]}" if i == id_i else f"${a.amount}" if i == cnt_i
                    else "0" if pt in PRIM or pt in INTS else "null" for i, (pt, pn) in enumerate(args)]
            print(f'"Any {et.name if et.kind == "enum" else "item"} (edit the value)=call:{target}({", ".join(vals)})"'
                  + (f"   # {', '.join(f'{n}={v}' for n, v in members[:8])}{' ...' if len(members) > 8 else ''}" if et.kind == "enum" else ""))
        for name, v in members if a.all or shown else members[:5]:
            vals = []
            for i, (pt, pn) in enumerate(args):
                if i == id_i:
                    vals.append(f"{et.name}.{name}" if et.kind == "enum" else str(v))
                elif i == cnt_i:
                    vals.append(f"${a.amount}")
                else:
                    vals.append("0" if pt in PRIM or pt in INTS else "null")
            print(f'"{name}=call:{target}({", ".join(vals)})"')
        if not a.all and len(members) > 5:
            print(f"# ... {len(members) - 5} more members of {et.full} (--all)")
        shown += 1
    # methods that take the item as an object (AddItem(ItemData, int)): the object comes from a list / array / dictionary of
    # such objects in the static tree, element picked by an editable cell -> one rule gives any item of the game
    done = []
    for m, why in rejected[:12]:
        objs = [(i, pt) for i, (pt, pn) in enumerate(m.args) if pt not in PRIM and pt not in INTS and (ot := res.find_type(pt)) and ot.kind == "class"]
        if not objs:
            continue
        colls = {}
        for i, pt in objs:
            c = await collection_path(res, rt, read, rt.base, res.find_type(pt))
            if c:
                colls[i] = c
        if len(colls) != len(objs):
            continue
        r = await receiver(m)
        if not r:
            continue
        vals = []
        for i, (pt, pn) in enumerate(m.args):
            et = res.find_type(pt)
            vals.append(colls[i][0] if i in colls else f"${a.amount}" if pt in INTS and COUNT_PARAM.search(pn) else "0" if pt in PRIM or pt in INTS
                        else f"${next(iter(real_values(et)), ('0', 0))[0]}" if et and et.kind == "enum" else "null")
        print(f"\n# {m.sig} RVA {m.rva:#x} [{r[1]}], " + ", ".join(f"{m.args[i][0]} {m.args[i][1]} = element of {p} ({n} in the dump, 0..{n - 1})" for i, (p, n) in colls.items()))
        print(f'"Any {m.args[objs[0][0]][0]} (edit the index)=call:{r[0]}{m.name}({", ".join(vals)})"')
        done.append(m)
    rejected = [(m, why) for m, why in rejected if m not in done]
    if rejected and not a.method:
        print("\n# give-like methods a trainer cannot call as is (object parameters need a path to an existing object, see README):")
        for m, why in rejected[:12]:
            vals = []
            for pt, pn in m.args:
                et = res.find_type(pt)
                vals.append(f"<{pt}.Member>" if et and et.kind == "enum" else "$1" if pt in PRIM else f"<path to {pt}>")
            this = f"{m.cls.name}." if m.static else f"<path to {m.cls.name}>."
            print(f'#   {m.sig}: {why}  ->  "Name=call:{this}{m.name}({", ".join(vals)})"')


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("dumpdir")
    ap.add_argument("--json", default="dump.json")
    ap.add_argument("--module", default="Il2CppUserAssemblies.prx")
    ap.add_argument("--enum", help="use this enum as the item list")
    ap.add_argument("--method", help="only give methods with this name")
    ap.add_argument("--all", action="store_true", help="one spec per enum member (default: 5 examples per method)")
    ap.add_argument("--limit", type=int, default=6, help="give methods to show (default 6)")
    ap.add_argument("--amount", default="1", help="default of the amount cell (default 1)")
    asyncio.run(amain(ap.parse_args()))
