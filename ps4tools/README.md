# ps4tools

Python helpers around Il2CppDumper for Unity IL2CPP games on PS4 / PS5 with [ps4debug](https://github.com/GoldHEN/ps4debug)
(same workflow as the Unreal tools in [ps4-unreal-dumper](https://github.com/TetzkatLipHoka/ps4-unreal-dumper)).

Requirements: Python 3.10+, `numpy`, and for live access the `ps4debug` Python module. `ps4dump.py` from
ps4-unreal-dumper makes the memory dumps (`dump.bin` + `dump.json`).

| Tool | Does |
|---|---|
| `il2mem.py <dumpdir>` | pulls `global-metadata.dat` and a loadable image of `Il2CppUserAssemblies.prx` out of a memory dump, so Il2CppDumper runs without touching the PKG. Run the dumper (this fork, any flavour) on the two outputs with the stock config.json and put the result in `<dumpdir>/sdk`; the ELF carries its base, so there is no dump-address prompt. |
| `il2live.py <dumpdir> "<path>" [--host IP] [--set V]` | reads / writes a value by a path that starts at a static field (or at an object of a class: `Player#0.health.health`, `--instances Player` lists them; dump session only). Without `--host` it resolves against the dump (offline check), with `--host` live. `--find mana` lists every number/bool field reachable from a static field whose path contains the word as a camelCase/snake token or token sequence anywhere after the root class (`CurrentStats{Type=SpellManaCurrent}.baseValue`, `MainActor._ActorModel.HP._Value`; "mana" does not match "Manager"; `heal*` / `*hp` / `max*hp` are wildcards anchored at a token), hits with the word in the field name first; an object field that matches by name is listed with its class and address. `--find 50` lists every field with that value; `--depth` hops, default 7 (a few seconds on a dump); `--types int,float,double` keeps only those field types, `--objects` also lists matching object fields with class and address. `"<path>" --fields` prints every field of the object the path points to with its value (what sits next to a value you found). `--methods damage` lists the methods with code whose name has the word (no word: the usual cheat targets - damage, spend, consume, heal, unlock ...), classes with live objects first, each with a ready `patch:` / `call:` spec for il2cheat. |
| `il2diff.py <dumpdir> a.json b.json --eq 50 77` | two dumps of one session, value before and after: every matching address, walked back to a static field and printed as an il2live path. |
| `il2items.py <dumpdir> [--all] [--enum E] [--method M]` | item cheats proposed from the dump: the item enum (ItemID-like, many members), the game's give methods (Add/Give/Grant... with an enum/int id and an optional count) and a path to their object (static roots, depth 4) or the hook to take `this` from, printed as `call:` specs for il2cheat. Per give method one generic rule first (`Any Weapons (edit the value)=call:...($Revolver, $1)`: the item is an editable cell, enum members = their numbers) and then one rule per member. Methods that take item objects (`AddItem(ItemData, int)`) get the object from a non-empty List / array / Dictionary of such objects in the static tree, element picked by a cell: `AddItem(LevelController::cachedCollectibles[$0], $1)`; when no such collection is reachable the method is listed with a spec template (`<path to Ammunition>`). The ReaperPy idea, no GUI. |
| `il2cheat.py <dumpdir> out.TLH "Name=path=value" "Name=call:Path.Method(args)" "Name=patch:Class.Method=noop" ...` | TLH trainer from il2live paths: one StartUP injection on a per-frame method (`Update`, `LateUpdate`, `OnUpdate`, `Tick`, ...) of a game class with one live instance, auto-picked from the assemblies the paths' root classes live in, classes the paths pass through first (the Hero whose hp you write surely ticks while the value exists; scene-bound names like Credits/Menu/Loading last; `--hook Class` or `--hook Class.Method` to choose, `IL2CHEAT_LIST_HOOKS=1` lists the candidates), per cheat a flag and a value cell; every path is resolved from its static root on every frame through the il2cpp TypeInfo table, so the trainer survives restarts. `--check path` prints the hops and compares them with il2live against the dump. Needs capstone. Three cheat kinds: `Name=path=value` writes the value every frame while on; `Name=call:Path.Method(args)` calls the game's own method once per switch-on (`PlayerData::instance.inventory.AddAmmo(PlayerData::instance.inventory.ownedAmmo[1], $5)`, `this.health.SetHealth(50, 0)`, static `UnityEngine.Time.set_timeScale(0.3)`; arguments are numbers, enum members, true/false, null, `$n` / `$Member` for an editable cell with default n / the enum member's number, or a path for an object parameter; `[$n]` / `{$n}` in a path pick the element by a cell); `Name=patch:Class.Method=noop|true|false|<number>` overwrites the method start with a return (TLH Assembly entry, toggled by the menu, no hook needed; overloads as `Method(int, int)`). Paths may start at the hooked object: `this.health.health` (rdi of the hooked Update), for games without a static root. |
| `il2diff.py <dumpdir> a.json --addr 0x203f12318 [...]` | one dump and the address of the value (found with any scanner, e.g. Phoenix Studio): only the backward walk to a static field, about 30 s. Without a static root it prints the owner chain (which class/field holds the value). |
| `il2diff.py <dumpdir> a.json b.json --changed [--class Name] [--same c.json]` | no value needed: every int / float / bool / enum field of a game object that differs between the dumps, then paths for the first hits. `--same` is a third dump of the unchanged state that filters moving values. |

Path syntax, passed through GUIs unchanged:

```
Class::field            static field of Class (root); namespace optional: Ns.Class::field, nested classes Outer.Inner
                        also a static of a base class: Player::<Instance>k__BackingField for Player : MonoSingleton<Player>
                        (generic bases are reached through the class's own TypeInfo entry plus klass.parent hops)
this.field              il2cheat: the object whose Update() is hooked (--hook Class); no static root needed
Class#n.field           il2live: the n-th object of Class in the dump (--instances Class); the address is session-bound
.field                  instance field, base class fields included
[i]                     element i of an array or List<T>
[$n]  {$n}              il2cheat: the index / int or enum key comes from an editable trainer cell, default n (il2live reads it as [n] / {n});
                        one cheat for every slot or item: `ownedAmmo[$1].amount=999`, `AddItem(ItemDatabase::instance.items[$0], $1)`
{42} {text}             Dictionary entry by int or string key
{Type=HealthCurrent}    Dictionary<System.Type, ...> entry by the type it stands for
{:ManaCaster}           Dictionary<int, SomeClass> entry by the class of its value (type caches: their int keys are hash codes that change per session)
{_guid=...} {name=...}  Dictionary entry by an identifier field of the key object
{#3}                    Dictionary entry by index (last resort)
{:GameEntity} {#0}      HashSet<T> element by the class of the element (when unique in the set) or by position among the used slots
:Class                  downcast (normally automatic: the object's real class is read from its klass pointer)
```

Example (Castlevania: Belmont's Curse, PS5):

```
python il2mem.py castle                                   # castle/ holds dump.bin + dump.json
Il2CppDumper castle/Il2CppUserAssemblies.prx.elf castle/global-metadata.dat castle/sdk
python il2diff.py castle dump_mana_50.json dump_mana_77.json --eq 50 77
python il2live.py castle "GameStateManager::_instance._mainCharacterEntity.componentCache{609408304}.CurrentStats{Type=HealthCurrent}.baseValue" --host 192.168.0.10 --set 999
python il2cheat.py castle "Castlevania_PPSA35399.TLH" --game "Castlevania: Belmont's Curse" --version 1.00 "Health 999=GameStateManager::_instance._mainCharacterEntity.componentCache{609408304}.CurrentStats{Type=HealthCurrent}.baseValue=999"
```

Trainer notes: `call:` cheats run inside the hook cave: the paths are resolved first (flag stays 1 and the call is retried next frame
until every object exists), then the flag goes to 2 and the method is called System V style (`this`, arguments, `MethodInfo* = 0`,
floats in xmm0..). A method may throw (a `NullReferenceException` in MOUSE's `TryUnlockingWeapon` ended the process with
"terminate is called": il2cpp raises a C++ exception, the unwinder found no unwind info for the cave's return address). So the
cave pops its frame, builds a frame shaped like a module function's (`push rbp; mov rbp, rsp; push rbx...`, found through the
module's `.eh_frame` by `ehframe.py`) with the hooked method's return address above it and lets the method return into that
function's `pop rbp; ret`: the unwinder reads that row and continues at the hooked method's caller, where il2cpp's invoke catch
logs the exception as usual; on a normal return the gadget pops the cave's continuation and the hooked method runs normally.
`MethodInfo* = 0` is enough for plain methods; a method that reads it (generic sharing, some virtual thunks) would crash, so
test a new call on the console with a save you can lose. `patch:` cheats are
TLH `Assembly` entries at the method's first bytes (`mov eax, 1` / `ret`; unique 16+ byte AOB in the module text) and hit every
caller, enemies included; a method that is inlined into its callers cannot be patched this way (il2cpp rarely inlines across
methods, the dumper's RVA is the out-of-line body). Both kinds follow ReaperPy's unity_items / values_auto (MIT, Ston3dd) in idea,
the code is il2cheat's own. The hook entry uses `Section-Name` `Il2CppUserAssemblies.prx` with `Section-Protection` 5 (text segment, AOB unique inside it; uTrainer/Phoenix tags, the cheat menu PRX reads them too) and
`ModuleBase+offset` symbols for the TypeInfo table and the metadata pointer, loaded with `movabs rax, Symbol` (a plain
`mov` with an address above 0x7FFFFFFF is sign-extended by older keystone builds, movabs forces the 64-bit immediate). Dictionary hops with int keys, `{Type=X}` keys and `{:Class}` keys are matched at runtime
(an int key of a `Dictionary<int, SomeClass>` is turned into `{:Class}` when that class is unique in the dictionary,
because such keys are per-session hash codes), `{_guid=...}` and string keys use the entry index seen in the dump
(entry order only changes when something is removed from the dictionary). Flag/Val cells are GetMem cells addressed
as `[Flag1]`, like the Unreal trainers.

Notes measured on real dumps (metadata v29 / v31 / v39, x64):

* metadata v39 (Unity 6): header entries are (offset, size, count) triples, `Il2CppTypeDefinition` is 76 or 82 bytes depending on the
  build (Unity 6000.3.13f1: 82, the dumper reports it as `39,1`), the tools take the size from the header count; nothing else in
  the runtime structures changed (Il2CppClass, TypeInfo table, metadata pointer)

* object header 0x10 (`klass*`, `monitor*`); dump.cs class field offsets include it, struct offsets do not
* `Il2CppClass`: name 0x10, namespace 0x18, declaringType 0x50, parent 0x58, generic_class 0x60 (-> +8 class_inst -> +8 type_argv), static_fields 0xB8
* open generic classes have no field offsets in dump.cs (all `0x0`): the tools lay them out sequentially behind the fields of the
  base class with natural alignment, a type parameter as 8 bytes (`SyncValue<T>`: `_Value` 0x10, `OnValueChanged` 0x18;
  `BehaviourMachine<T> : MonoBehaviour` starts at 0x18 behind `m_CachedPtr`; wrong for struct parameters)
* value-type fields (`Vector3`, `Color`, own structs) are inline: `--find` walks their fields (`.position.x`), no pointer hop
* statics of a generic base (`Player : MonoSingleton<Player>`) are reached as `TypeInfo[idx(Player)].parent.static_fields`,
  the generic instance class itself is not in the TypeInfo table
* arrays: elements from 0x20; `List<T>`: `_items` 0x10, `_size` 0x18; `Dictionary<K,V>`: `_entries` 0x18, `_count` 0x20, entry = {int hash, int next, key @8, value @0x10}; `HashSet<T>`: `_slots` 0x18, `_count` 0x20, slot = {int hash, int next, value @8} (0x10 bytes, free slots have hash < 0)
* Entitas games (Cat Quest III): entities live in `HashSet` fields of contexts and groups, the player is `SomeManager::_instance.playerEntities._entities{:GameEntity}` or `Contexts::_sharedInstance.<game>k__BackingField._groupsForIndex[i][0]._entities{#0}`, components by index: `._components[57].value`
* static roots and classes are resolved in the running process through the il2cpp TypeInfo table, so the dump may come from an earlier session of the same build; instance addresses in `--eq`/`--changed` output are only valid for the session the dumps came from
* the first run on a dump builds `<dump>.bin.klasses.json` (about a minute), later runs take seconds
* values shown on screen are not always the stored ones (a marker counter showed 5 while the list had 11 entries): when `--eq` finds nothing, use `--find` by name or `--changed`
