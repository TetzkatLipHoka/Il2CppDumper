"""Propose item cheats for a Unity IL2CPP game from the dump: the item enum, the game's own give method and how to reach its
object, printed as ready il2cheat specs (the ReaperPy unity_items idea, without the GUI).

    python il2items.py <dumpdir>                 # best enum + give methods, 5 example specs per method
    python il2items.py <dumpdir> --all           # one spec per enum member for the best give method
    python il2items.py <dumpdir> --enum Weapons --method AddAmmo

Ranking is by name (ItemID-like enums with many members; Add/Give/Grant... methods with an enum/int id parameter and an
optional count), game assemblies only. An instance method needs an object: il2items searches the static roots (depth 4)
for one of the owner class and prints the path, or suggests hooking the owner's Update and calling this.Method(...).
Object parameters (ItemData, Ammunition) cannot be made up: those methods are listed with the reason, a path to an
existing object can be given by hand (see README).
"""
import argparse, asyncio, os, re, sys
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


async def object_path(res, rt, read, base, owner, depth=4):
    """Shortest path from a static root to an object of class `owner` (or a subclass) in the dump, or None."""
    want = {c.full for c in res.types.values() if any(x is owner for x in res.chain(c))}
    frontier, seen = [], set()
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
            if il2live.value_format(res, ftype) == "Q":
                try:
                    obj = await il2live.read_u64(read, addr)
                    ot = rt.object_type(obj) if obj else None
                except LookupError:
                    ot = None
                if ot and ot.full in want:
                    return path
            for child in await il2live.children(res, rt, read, path, addr, ftype):
                if child[1] not in seen:
                    seen.add(child[1]); nxt.append(child[:3])
        frontier = nxt
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
    shown = 0
    for m, id_i, cnt_i, et in gives[:a.limit]:
        if a.method and m.name != a.method:
            continue
        et = et or best
        args = m.args
        if m.static:
            target, note = f"{m.cls.name}.{m.name}", "static"
        else:
            path = await object_path(res, rt, read, rt.base, m.cls)
            hooks = [h for h in m.cls.methods if h in ("Update", "LateUpdate", "FixedUpdate")]
            if path:
                target, note = f"{path}.{m.name}", f"object via {path}"
            elif hooks and il2live.instances_of(res, rt, dump, m.cls):
                target, note = f"this.{m.name}", f"no static path; hook the owner: --hook {m.cls.name}.{hooks[0]}"
            else:
                print(f"# {m.sig}: no static path to a {m.cls.name} object and no per-frame method to hook")
                continue
        members = real_values(et) if et.kind == "enum" else [(f"id{v}", v) for v in range(1, 6)]
        print(f"\n# {m.sig} RVA {m.rva:#x} [{note}], id = {args[id_i][0]} {args[id_i][1]}" + (f", count = {args[cnt_i][1]}" if cnt_i is not None else ""))
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
