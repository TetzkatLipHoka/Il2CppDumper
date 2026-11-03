"""Generate a TLH trainer (cheat menu / Phoenix Studio import) from il2live paths of a Unity IL2CPP game (PS4/PS5).

    python il2cheat.py <dumpdir> out.TLH "Mana=GameStateManager::_instance._mainCharacterEntity.componentCache{611004928}.manas[0]._currentManaStatObject.baseValue=999" ...
    python il2cheat.py <dumpdir> out.TLH --hook PlayerLifeBar "Name=path=value" ...
    python il2cheat.py <dumpdir> --check "path"           # emulate the generated hops against the dump, compare with il2live
    python il2cheat.py <dumpdir> out.TLH --hook Player "Health=this.health.health=999"         "Ammo=call:PlayerData::instance.inventory.AddAmmo(PlayerData::instance.inventory.ownedAmmo[1], $5)"         "Slow=call:UnityEngine.Time.set_timeScale(0.3)" "No damage=patch:PlayerHealth.GetDamage=noop"

Cheat kinds: "Name=path=value" writes the value every frame while on (int/float/bool/byte/short/long/enum fields); the path is
il2live syntax (Class::static or this. for the hooked object, .field, [i] / [$n] (index from a cell), {key} / {$n}, {Type=X}, :Cast). "Name=call:Path.Method(args)"
calls the game's method once per switch-on from the hook cave (System V, MethodInfo* = 0; args: numbers, enum members, true/false,
null, $n = editable cell, a path = object). "Name=patch:Class.Method[(types)]=noop|true|false|<n>" is a TLH Assembly entry at the
method start (return value forced / method skipped), toggled by the menu, no hook. The call/patch kinds follow ReaperPy's idea. The hook is the first byte of
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
import il2live
from il2live import KLASS_STATICS, KLASS_PARENT, PRIM, split_generic, elem_size, instances, instances_of

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
async def compile_path(res, rt, read, base, path, classes=None, this=None):
    """Path -> hops. Object classes behind pointers are read from the dump (auto downcast like il2live), string/_guid
    dictionary keys are resolved to their entry index in the dump. this = (Type, dump address) of the hooked object for
    'this.' paths (rdi at the hook); Class#n roots are dump addresses and are refused."""
    segs = res.tokens(path)
    first = False
    if segs[0][0] == "obj":
        if segs[0][1][0] != "this":
            sys.exit(f"{path}: Class#n is a dump address, a trainer cannot use it; start at this. (the hooked object) or a static field")
        if this is None:
            sys.exit(f"{path}: a this. path needs the hook class (--hook Class, or a static-rooted cheat before it so the hook is chosen first)")
        t, _ = this
        hops, ftype, cur_t, first = [("this", t)], t.full, t, True
    else:
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
            if first:
                first = False                           # rax already is the object
            elif inline:
                cur_t = ct
            else:
                hops.append(("deref",))
                obj = await emulate(rt, read, base, hops, this and this[1])
                cur_t = (await rt.object_type_live(read, obj) if obj else None) or res.find_type(ftype, cur_t.ns if cur_t else "")
                if cur_t is None:
                    sys.exit(f"unknown class for field type {ftype}")
                if classes is not None:
                    classes.add(cur_t.full)                 # objects on the way (Hero, AgentStats): their Update() surely runs while the value exists
            f = res.field(cur_t, arg) or sys.exit(f"{cur_t.full} has no field {arg}")
            off, ft, owner = f
            ftype = res.subst(ftype, owner, ft)
            if off:
                hops.append(("add", off))
        elif op == "index":
            etype = gargs[0] if base_name == "List" else ftype[:-2]
            if arg.startswith("$"):                                          # [$n]: index from an editable cell, default n
                hops += [("deref",), ("index_cell", int(arg[1:] or "0", 0), elem_size(res, etype), base_name == "List")]
            else:
                hops += [("deref",), ("index", int(arg, 0), elem_size(res, etype), base_name == "List")]
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
                if arg.startswith("$"):                                      # {$n}: key from an editable cell, default n
                    hops.append(("key_int_cell", int(arg[1:] or "0", 0))); ftype = vtype; continue
                hops.append(("key_int", int(arg, 0)))
                if vtype not in PRIM:                           # int keys of a type cache are per-session hash codes: match the value's class instead
                    d = await emulate(rt, read, base, hops[:-1], this and this[1])
                    e = d and await emulate(rt, read, base, hops, this and this[1])
                    names = e and await il2live.dict_key_names(res, rt, read, ktype, e - 0x10, vtype, d)
                    if names and names[0].startswith(":"):
                        ct = res.find_type(names[0][1:])
                        hops[-1] = ("key_class", ct.idx, ct.full)
                        print(f"  {{{arg}}} -> {{{names[0]}}} (int key is a per-session hash, the value's class is unique in the dictionary)")
            else:                                               # string / object key: entry index from the dump
                d = await emulate(rt, read, base, hops, this and this[1]) or sys.exit(f"{arg}: dictionary is null in the dump")
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
def asm_hops(rt, hops, fail, cells=None):
    """cells: [(symbol, default)] of the [$n] / {$n} cells the code reads (4-byte integers), appended here."""
    code, cells = [], [] if cells is None else cells
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
        elif k == "this":
            code += ["mov rax, rdi", "test rax, rax", f"jz {fail}"]                                   # rdi = this of the hooked Update()
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
        elif k in ("index_cell", "key_int_cell"):            # [$n] / {$n}: index or int key from an editable cell
            cell = f"{'Idx' if k == 'index_cell' else 'Key'}{fail[:-4]}_{len(cells)}"
            cells.append((cell, h[1]))
            if k == "index_cell":
                code += [f"mov ecx, dword ptr [{cell}]", "cmp dword ptr [rax+0x18], ecx", f"jbe {fail}"]       # unsigned: a negative cell fails too
                if h[3]:
                    code += ["mov rax, [rax+0x10]", "test rax, rax", f"jz {fail}", "cmp dword ptr [rax+0x18], ecx", f"jbe {fail}"]
                code += [f"imul rcx, rcx, {h[2]:#x}", "lea rax, [rax+rcx+0x20]"]
            else:
                lbl = fail.replace("_end", "") + f"_k{len(code)}"
                code += ["mov rdx, [rax+0x18]", "test rdx, rdx", f"jz {fail}", "mov ecx, dword ptr [rax+0x20]", "add rdx, 0x20",
                         f"mov r8d, dword ptr [{cell}]", f"{lbl}_loop:", "test ecx, ecx", f"jz {fail}",
                         "cmp dword ptr [rdx+8], r8d", f"je {lbl}_found", "add rdx, 0x18", "dec ecx", f"jmp {lbl}_loop",
                         f"{lbl}_found:", "lea rax, [rdx+0x10]"]
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
                code += ["movabs r8, MetadataPtr", "mov r8, [r8]", f"add r8, {rt.td_off + h[1] * rt.td_size:#x}"]    # Il2CppTypeDefinition* of the key type
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


def cell_entries(cells):
    """[$n] / {$n} cells -> GetMem lines and TLH value entries."""
    return ([f"GetMem( {c}, 4 )" for c, _ in cells],
            [f"      <Symbol>{c}</Symbol>\n      <Type>Value</Type>\n      <ValueType>Integer</ValueType>\n      <Value>{d}</Value>" for c, d in cells])


# ---- emulation of the hops against the dump (self check, the asm is not executed here) ---------------------------------
async def emulate(rt, read, base, hops, this_obj=None):
    a = None
    for h in hops:
        k = h[0]
        if k in ("index_cell", "key_int_cell"):                          # the cell holds its default in the dump check
            h = (k[:-5],) + h[1:]; k = h[0]
        if k == "this":
            a = this_obj
        elif k == "root":
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
            want = meta + rt.td_off + h[1] * rt.td_size if k == "key_type" else h[1]
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
def module_text(rt, dump):
    text = [r for r in dump.regs if r["name"] == rt.module and r["prot"] & 4][0]
    return text, dump.m[text["offset"]:text["offset"] + text["end"] - text["start"]]


def unique_aob(blob, rva):
    """Shortest 16..92 byte pattern at rva that occurs once in the module's text, else None."""
    for length in range(16, 96, 4):
        pat = bytes(blob[rva:rva + length])
        if blob.count(pat) == 1:
            return pat
    return None


def pick_hook(rt, res, dump, script, want=None, images=("Assembly-CSharp.dll",), roots=()):
    """(method name, RVA, aob bytes, site instructions, live objects, hook Type) for an Update() of a game class with live instances."""
    import capstone
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    text, blob = module_text(rt, dump)
    counts = {k: len(v) for k, v in instances(rt, dump).items()}
    for t in res.types.values():                     # an Update() of a base class runs for the instances of its subclasses too
        n = sum(counts.get(k, 0) for k in rt.by_full.get(t.full, []))
        if n:
            for c in list(res.chain(t))[1:]:
                for k in rt.by_full.get(c.full, []):
                    counts[k] = counts.get(k, 0) + n
    cands = []
    tokens = {r.split(".")[-1].lower() for r in roots if len(r.split(".")[-1]) >= 5}   # class names seen on the paths, as substrings
    want_cls, _, want_meth = want.partition(".") if want else (None, None, None)   # --hook Class or --hook Class.Method
    for e in script["ScriptMethod"]:
        cls, _, meth = e["Name"].rpartition("$$")
        if (meth not in HOOK_METHODS and meth != want_meth) or "<" in cls:
            continue
        if want and (cls.split(".")[-1] != want_cls or (want_meth and meth != want_meth)):
            continue
        t = res.find_type(cls)
        if not t or (not want and t.image not in images and t.image.startswith(il2live.GAME_IMAGE_SKIP)):   # game code only (Mouse.dll counts)
            continue
        n = sum(counts.get(k, 0) for k in rt.by_full.get(t.full, []))
        if n:
            core = 2 if re.search(r"Credits|Menu|Title|Debug|Test|Loading|Tutorial|Intro|Splash|Demo|Cutscene|Developer|Recorder|Editor|Preview|Painter|FPSCounter", cls) else \
                0 if re.search(r"Manager|System|Controller|Player|Game|Hud|HUD|Input|Pad", cls) else 1   # scene-bound objects exist but do not tick in-game
            unity_msg = meth in ("Update", "LateUpdate", "FixedUpdate") and any(c.name == "MonoBehaviour" for c in res.chain(t))
            if unity_msg:                                     # called by the engine through the method pointer, never inlined
                weak = False
            else:                                             # custom per-frame method: a private one may be inlined into its caller
                weak = t.methods.get(meth) == "private"
            prio = HOOK_METHODS.index(meth) if meth in HOOK_METHODS else len(HOOK_METHODS)
            # a dump keeps dead objects of earlier scenes, so "one instance" is weaker than a core name: Shogun Showdown had
            # CombatManager x3 (one live) next to CreditsSceneManager x1
            related = any(tok in cls.lower() for tok in tokens)   # ScriptableManagerManager for a path through ScriptableManager objects
            cands.append((not unity_msg, t.full not in roots, core, not related, n != 1, weak, prio, n, cls, meth, e["Address"], t))
    if want is None and os.environ.get("IL2CHEAT_LIST_HOOKS"):
        for c in sorted(cands, key=lambda c: c[:-1])[:25]:
            print(f"  candidate {c[8]}.{c[9]} instances={c[7]}{'' if not c[0] else ' (custom)'}{' (private)' if c[5] else ''}{' (on path)' if not c[1] else ' (related)' if not c[3] else ''}", file=sys.stderr)
    for *_, n, cls, meth, rva, t in sorted(cands, key=lambda c: c[:-1]):
        site, size = [], 0
        for ins in md.disasm(blob[rva:rva + 32], text["start"] + rva):
            if "rip" in ins.op_str or (not site and ins.mnemonic == "jmp"):    # rip-relative, or a thunk that only jumps on
                site = None; break
            site.append(f"{ins.mnemonic} {ins.op_str}".strip()); size += ins.size
            if size >= 5:
                break
        if not site:
            continue
        pat = unique_aob(blob, rva)
        if pat:
            return f"{cls}.{meth}", rva, pat, site, n, t
    sys.exit("no usable per-frame hook (no candidate with live instances, or all start rip-relative / have no unique AOB); try --hook Class or --hook Class.Method")


def xml_escape(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


# ---- call: / patch: cheats (the ReaperPy unity_items / values_auto idea on the il2cheat hook) ---------------------------
INT_REGS = ["rdi", "rsi", "rdx", "rcx", "r8", "r9"]
REG32 = dict(rdi="edi", rsi="esi", rdx="edx", rcx="ecx", r8="r8d", r9="r9d")
INTS = ("bool", "sbyte", "byte", "short", "ushort", "int", "uint", "long", "ulong", "char", "IntPtr", "UIntPtr")


def split_args(text):
    out, depth, cur = [], 0, ""
    for ch in text:
        depth += ch in "<[({"; depth -= ch in ">])}"
        if ch == "," and depth == 0:
            out.append(cur.strip()); cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


def is_path(text):
    return "::" in text or text.startswith("this.")


def ret_asm(res, ret, mode, who):
    """Assembly that returns `mode` from a method whose return type is `ret` (TLH Assembly entry at the method start)."""
    et = res.find_type(ret)
    base = et.enum_base if et and et.kind == "enum" else ret
    if mode == "noop":
        if ret != "void":
            sys.exit(f"{who}: returns {ret}, 'noop' is for void methods; use true/false or a number")
        return "ret"
    if ret == "void":
        sys.exit(f"{who}: is void, use noop")
    if mode in ("true", "false"):
        if base != "bool":
            sys.exit(f"{who}: returns {ret}, not bool; give a number")
        return f"mov eax, {int(mode == 'true')}\nret"
    if base == "float":
        return f"mov eax, {struct.unpack('<I', struct.pack('<f', float(mode)))[0]:#x}\nmovd xmm0, eax\nret"
    if base == "double":
        return f"movabs rax, {struct.unpack('<Q', struct.pack('<d', float(mode)))[0]:#x}\nmovq xmm0, rax\nret"
    if base in INTS:
        v = int(mode, 0) if base != "bool" else int(mode.lower() in ("1", "true"))
        return (f"movabs rax, {v & 0xFFFFFFFFFFFFFFFF:#x}" if base in ("long", "ulong", "IntPtr", "UIntPtr") else f"mov eax, {v & 0xFFFFFFFF:#x}") + "\nret"
    sys.exit(f"{who}: return type {ret} is an object/struct, not patchable")


async def compile_call(res, rt, read, base, k, target, this_info, roots, images):
    """'Path.Method(args)' or 'Class.Method(args)' (static) -> (asm lines, GetMem lines, RegisterSymbol lines, cheat value entries, text).
    Arguments: numbers, enum members (Weapons.Revolver or Revolver), true/false, null, $n / $Member (editable value cell with default n),
    or a path (Class::... / this....) for an object parameter. System V order (this, args..., MethodInfo* = 0); floats in xmm."""
    m = re.match(r"^(?P<target>.+?)\((?P<args>.*)\)$", target) or sys.exit(f"{target}: expected Path.Method(args)")
    obj_path, _, mname = m["target"].rpartition(".")
    args = split_args(m["args"])
    mems, syms, entries, code, cells = [], [], [], [], []
    if is_path(obj_path):
        hops, ftype = await compile_path(res, rt, read, base, obj_path, roots, this_info)
        hops.append(("deref",))                                                  # the path names the slot, this = the object in it
        obj = await emulate(rt, read, base, hops, this_info and this_info[1])
        t = (rt.object_type(obj) if obj else None) or res.find_type(ftype) or sys.exit(f"{obj_path}: unknown class {ftype}")
        meth = res.method(t, mname, len(args))
        if meth.static:
            sys.exit(f"{meth.sig} is static, call it as {t.name}.{mname}(...)")
        mems.append(f"GetMem( This{k}, 8 )")
        code += asm_hops(rt, hops, f"c{k}_end", cells) + [f"mov [This{k}], rax"]
        if hops[0][0] == "root":
            images.add(hops[0][1].image)
    else:
        t = res.find_type(obj_path) or sys.exit(f"{target}: class {obj_path} not in dump.cs")
        meth = res.method(t, mname, len(args))
        if not meth.static:
            sys.exit(f"{meth.sig} needs an object: call it as <path to a {t.name}>.{mname}(...)")
    params = meth.args
    if len(args) != len(params):
        sys.exit(f"{meth.sig}: {len(params)} parameters, {len(args)} arguments given")
    ints, floats, loads = (0 if meth.static else 1), 0, []
    for i, ((ptype, pname), text) in enumerate(zip(params, args)):
        pt = res.find_type(ptype)
        enum = bool(pt and pt.kind == "enum")
        base_t = pt.enum_base if enum else ptype
        isfloat = base_t in ("float", "double")
        if isfloat:
            reg = f"xmm{floats}"; floats += 1
        else:
            if ints >= len(INT_REGS) - 1:
                sys.exit(f"{meth.sig}: too many integer/object parameters for register passing")
            reg = INT_REGS[ints]; ints += 1
        who = f"{meth.sig} argument {i + 1} ({ptype} {pname})"
        if text.startswith("$"):                                                 # editable cell
            if not (isfloat or base_t in INTS):
                sys.exit(f"{who}: $ cells are for numbers/enums/bools")
            tlh, size, _r, _f = CELL[base_t if base_t in CELL else "int"]
            default = text[1:] or "1"
            if enum and not default.lstrip("-").isdigit():
                default = str(pt.consts.get(default.split(".")[-1]) if default.split(".")[-1] in pt.consts else sys.exit(f"{who}: {default} is not a member of {pt.full}"))
            mems.append(f"GetMem( Val{k}_{i}, {size} )")
            entries.append(f"      <Symbol>Val{k}_{i}</Symbol>\n      <Type>Value</Type>\n      <ValueType>{tlh}</ValueType>\n      <Value>{default}</Value>")
            if isfloat:
                loads += [f"mov {'rax' if size == 8 else 'eax'}, [Val{k}_{i}]", f"mov{'q' if size == 8 else 'd'} {reg}, {'rax' if size == 8 else 'eax'}"]
            elif size >= 4:
                loads.append(f"mov {reg if size == 8 else REG32[reg]}, [Val{k}_{i}]")
            else:
                loads.append(f"movzx {REG32[reg]}, {'byte' if size == 1 else 'word'} ptr [Val{k}_{i}]")
        elif is_path(text):                                                      # object argument from a path
            if base_t in INTS or isfloat:
                sys.exit(f"{who}: a path gives an object, the parameter is a {ptype}")
            hops, _ = await compile_path(res, rt, read, base, text, roots, this_info)
            hops.append(("deref",))                                              # object argument = the pointer in the slot
            mems.append(f"GetMem( Arg{k}_{i}, 8 )")
            code += asm_hops(rt, hops, f"c{k}_{i}_end", cells) + [f"mov [Arg{k}_{i}], rax"]
            loads.append(f"mov {reg}, [Arg{k}_{i}]")
            if hops[0][0] == "root":
                images.add(hops[0][1].image)
        elif text == "null":
            if base_t in INTS or isfloat:
                sys.exit(f"{who}: null is for object parameters")
            loads.append(f"xor {REG32[reg]}, {REG32[reg]}")
        elif isfloat:
            v = float(text)
            loads += [f"mov eax, {struct.unpack('<I', struct.pack('<f', v))[0]:#x}", f"movd {reg}, eax"] if base_t == "float" else \
                     [f"movabs rax, {struct.unpack('<Q', struct.pack('<d', v))[0]:#x}", f"movq {reg}, rax"]
        elif enum:
            name = text.split(".")[-1]
            v = int(text, 0) if text.lstrip("-").isdigit() else pt.consts.get(name)
            if v is None:
                sys.exit(f"{who}: {text} is not a member of {pt.full}: {', '.join(list(pt.consts)[:40])}")
            loads.append(f"mov {REG32[reg]}, {v & 0xFFFFFFFF:#x}")
        elif base_t == "bool":
            loads.append(f"mov {REG32[reg]}, {int(text.lower() in ('1', 'true'))}")
        elif base_t in INTS:
            v = int(text, 0)
            loads.append(f"movabs {reg}, {v & 0xFFFFFFFFFFFFFFFF:#x}" if base_t in ("long", "ulong", "IntPtr", "UIntPtr") else f"mov {REG32[reg]}, {v & 0xFFFFFFFF:#x}")
        else:
            sys.exit(f"{who}: {ptype} parameters take a path to an object or null")
    syms.append(f"RegisterSymbol( Call{k}, ModuleBase+{meth.rva:#x} )")
    cm, ce = cell_entries(cells); mems += cm; entries += ce
    code += [f"mov byte ptr [Flag{k}], 2",                                      # once per switch-on, only after every path resolved
             "push rdi", "push rsi", "push r10", "push r11", "sub rsp, 8"]       # entry rsp = 8 mod 16, 6 saves in the frame + 4 here: sub 8 aligns
    if not meth.static:
        code.append(f"mov rdi, [This{k}]")
    code += loads + [f"xor {REG32[INT_REGS[ints]]}, {REG32[INT_REGS[ints]]}",   # MethodInfo* = 0 (ponytail: enough for plain methods; generic/virtual thunks may read it)
                     f"movabs rax, Call{k}", "call rax", "add rsp, 8", "pop r11", "pop r10", "pop rsi", "pop rdi"]
    code += [f"c{k}_{i}_end:" for i in range(len(args))]
    return code, mems, syms, entries, f"{meth.sig} [{'static' if meth.static else 'this=' + obj_path}] RVA {meth.rva:#x}"


async def amain(a):
    dump = il2live.Dump(a.dumpdir, a.json)
    types = il2live.parse_dump_cs(os.path.join(a.dumpdir, "sdk", "dump.cs"))
    rt = il2live.Runtime(dump, types, a.module)
    res = il2live.Resolver(rt)
    if rt.table_off is None or rt.meta_off is None:
        sys.exit("TypeInfo table / metadata globals not found in the dump")
    script = json.load(open(os.path.join(a.dumpdir, "sdk", "script.json")))

    async def read(va, n):
        return dump.read(va, n)

    images, roots, hook = {"Assembly-CSharp.dll"}, set(), None       # game assemblies: Assembly-CSharp plus whatever the roots live in

    def need_hook():
        """Pick the hook once; a this. path needs it before its own compilation (the hooked class is the root)."""
        nonlocal hook
        if hook is None:
            hook = pick_hook(rt, res, dump, script, a.hook, images, roots)
            objs = instances_of(res, rt, dump, hook[5])
            hook = hook + ((hook[5], objs[0] if objs else None),)
            print(f"hook: {hook[0]} at {a.module}+{hook[1]:#x} ({hook[4]} live instance{'s' if hook[4] != 1 else ''}), AOB {len(hook[2])} bytes, site: {'; '.join(hook[3])}")
        return hook[6]

    def this_info(text):
        return need_hook() if "this." in text else (hook[6] if hook else None)

    if a.check:
        ti = this_info(a.check)
        hops, ftype = await compile_path(res, rt, read, rt.base, a.check, this=ti)
        emu = await emulate(rt, read, rt.base, hops, ti and ti[1])
        ref, _ = await il2live.follow(res, rt, read, rt.base, a.check, this_obj=ti and ti[1])
        print("\n".join(asm_hops(rt, hops, "c1_end")))
        print(f"\nemulated {emu and hex(emu)} vs il2live {ref and hex(ref)} -> {'OK' if emu == ref else 'MISMATCH'}")
        return

    cheats, blocks, mems, syms = [], [], [], []
    text, blob = module_text(rt, dump)
    for k, spec in enumerate(a.specs, 1):
        name, rest = spec.split("=", 1)                  # the path itself may contain "=" ({Type=X}, {_guid=...})
        entries = [f"      <Symbol>Flag{k}</Symbol>\n      <Type>Value</Type>\n      <ValueType>Boolean</ValueType>\n      <Value>0</Value>"]
        if rest.startswith("patch:"):                    # Name=patch:Class.Method[(types)]=noop|true|false|<number>: TLH Assembly entry, toggled by the menu
            target, mode = rest[6:].rsplit("=", 1)
            tm = re.match(r"^(?P<cls>[\w.]+)\.(?P<name>\w+)(?:\((?P<types>.*)\))?$", target) or sys.exit(f"{name}: expected patch:Class.Method[(types)]=mode")
            t = res.find_type(tm["cls"]) or sys.exit(f"{name}: class {tm['cls']} not in dump.cs")
            meth = res.method(t, tm["name"], types=[x.strip() for x in tm["types"].split(",") if x.strip()] if tm["types"] is not None else None)
            pat = unique_aob(blob, meth.rva) or sys.exit(f"{name}: no unique AOB at {meth.sig}")
            asm = ret_asm(res, meth.ret, mode, f"{name}: {meth.sig}")
            cheats.append((name, [], (pat, asm)))
            print(f"{name}: {meth.sig} RVA {meth.rva:#x} -> {asm.replace(chr(10), '; ')} (all callers, enemies too)")
            continue
        mems.append(f"GetMem( Flag{k}, 1 )")
        if rest.startswith("call:"):                     # Name=call:Path.Method(args): once per switch-on
            code, cm, cs, ce, text_ = await compile_call(res, rt, read, rt.base, k, rest[5:], this_info(rest), roots, images)
            blocks.append("\n".join([f"cmp byte ptr [Flag{k}], 1", f"jne c{k}_end"] + code + [f"c{k}_end:"]))
            mems += cm; syms += cs; entries += ce
            cheats.append((name, entries, None))
            print(f"{name}: call {text_}")
            continue
        path, value = rest.rsplit("=", 1)
        ti = this_info(path)
        hops, ftype = await compile_path(res, rt, read, rt.base, path, roots, ti)
        emu = await emulate(rt, read, rt.base, hops, ti and ti[1])
        ref, _ = await il2live.follow(res, rt, read, rt.base, path, this_obj=ti and ti[1])
        if emu != ref:
            sys.exit(f"{name}: hop emulation {emu and hex(emu)} differs from il2live {ref and hex(ref)}, codegen bug")
        vt = ftype
        et = res.find_type(ftype)
        if ftype not in CELL and et and et.kind == "enum":
            vt = et.enum_base
        if vt not in CELL:
            sys.exit(f"{name}: field type {ftype} not supported (number/bool/enum only)")
        tlh_type, size, vreg, fmt = CELL[vt]
        cells = []
        code = [f"cmp byte ptr [Flag{k}], 1", f"jne c{k}_end"] + asm_hops(rt, hops, f"c{k}_end", cells)
        cm, ce = cell_entries(cells); mems += cm; entries += ce
        if vt == "bool":
            code.append(f"mov byte ptr [rax], {int(value.strip().lower() not in ('0', 'false', 'no'))}")
        else:
            mems.append(f"GetMem( Val{k}, {size} )")
            code += [f"mov {vreg}, [Val{k}]", f"mov [rax], {vreg}"]
            entries.append(f"      <Symbol>Val{k}</Symbol>\n      <Type>Value</Type>\n      <ValueType>{tlh_type}</ValueType>\n      <Value>{value}</Value>")
        blocks.append("\n".join(code + [f"c{k}_end:"]))
        cheats.append((name, entries, None))
        print(f"{name}: {path} ({ftype}) = {value}, {len(hops)} hops, offline slot {ref and hex(ref)}")
        if hops[0][0] == "root":
            images.add(hops[0][1].image); roots.add(hops[0][1].full)
        roots.update(re.findall(r"\{Type=([\w.]+)\}", path))   # {Type=X} keys name the objects the path walks through as well

    info = json.load(open(os.path.join(a.dumpdir, a.json)))
    title = info.get("title_id", "")
    cusa = int(title[4:]) if title[4:].isdigit() else 0
    game = xml_escape(a.game or os.path.basename(a.out).split("_")[0])
    sec = ['      <Section>0</Section>', f'      <Section-Name>{a.module}</Section-Name>', '      <Section-Protection>5</Section-Protection>']
    xml = ['<?xml version="1.0" encoding="utf-8" standalone="no"?>',
           f'<Trainer xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
           f'Game="{game}" Creator="il2cheat" CUSA="{cusa}" Version="{a.version}" Process="eboot.bin" Legacy="1">']
    if blocks:
        need_hook()
        hook_name, rva, aob, site, n, _t, _ti = hook
        syms = [f"RegisterSymbol( TypeInfoTable, ModuleBase+{rt.table_off:#x} )", f"RegisterSymbol( MetadataPtr, ModuleBase+{rt.meta_off:#x} )"] + syms
        asm = "\n".join(mems + syms + ["", "pushfq", "push rax", "push rcx", "push rdx", "push r8", "push r9", ""]
                        + blocks + ["", "done:", "pop r9", "pop r8", "pop rdx", "pop rcx", "pop rax", "popfq"] + site)
        aob_s = "-".join(f"{b:02X}" for b in aob)
        xml += [f'  <StartUP Name="IL2CPP hook ({xml_escape(hook_name)})" Description="static roots via the il2cpp TypeInfo table, resolved every frame">',
                '    <Entry>', *sec, f'      <AOB>{aob_s}</AOB>', '      <Type>Injection</Type>', f'      <Assembly>{xml_escape(asm)}</Assembly>', '    </Entry>', '  </StartUP>']
    for name, entries, patch in cheats:
        xml.append(f'  <Cheat Name="{xml_escape(name)}" Description="">')
        for en in entries:
            xml += ['    <Entry>', '      <Section>0</Section>', en, '    </Entry>']
        if patch:
            xml += ['    <Entry>', *sec, f'      <AOB>{"-".join(f"{b:02X}" for b in patch[0])}</AOB>', '      <Type>Assembly</Type>', f'      <Assembly>{xml_escape(patch[1])}</Assembly>', '    </Entry>']
        xml.append('  </Cheat>')
    xml.append('</Trainer>')
    open(a.out, "w", encoding="utf-8-sig", newline="\n").write("\n".join(xml) + "\n")
    print(f"wrote {a.out}: {len(cheats)} cheats" + (f", hook {hook[0]}" if hook else ", no hook (patches only)"))


if __name__ == "__main__":
    import argparse, asyncio
    ap = argparse.ArgumentParser()
    ap.add_argument("dumpdir")
    ap.add_argument("out", nargs="?", help="output .TLH")
    ap.add_argument("specs", nargs="*", help='"Name=path=value" | "Name=call:Path.Method(args)" | "Name=patch:Class.Method=noop|true|false|<n>"')
    ap.add_argument("--json", default="dump.json")
    ap.add_argument("--module", default=MODULE)
    ap.add_argument("--hook", help="Class or Class.Method to hook (default: an Update-like method of an Assembly-CSharp class with one live instance); this. paths start at its object")
    ap.add_argument("--game", help="game name for the TLH header (default: from the output file name)")
    ap.add_argument("--version", default="", help="game version for the TLH header, e.g. 1.00")
    ap.add_argument("--check", help="path: print the generated hops and compare the emulation with il2live")
    a = ap.parse_args()
    if not a.check and not (a.out and a.specs):
        ap.error("out.TLH and at least one spec, or --check path")
    asyncio.run(amain(a))
