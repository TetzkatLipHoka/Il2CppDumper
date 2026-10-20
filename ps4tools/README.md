# ps4tools

Python helpers around Il2CppDumper for Unity IL2CPP games on PS4 / PS5 with [ps4debug](https://github.com/GoldHEN/ps4debug)
(same workflow as the Unreal tools in [ps4-unreal-dumper](https://github.com/TetzkatLipHoka/ps4-unreal-dumper)).

Requirements: Python 3.10+, `numpy`, and for live access the `ps4debug` Python module. `ps4dump.py` from
ps4-unreal-dumper makes the memory dumps (`dump.bin` + `dump.json`).

| Tool | Does |
|---|---|
| `il2mem.py <dumpdir>` | pulls `global-metadata.dat` and a loadable image of `Il2CppUserAssemblies.prx` out of a memory dump, so Il2CppDumper runs without touching the PKG. Run the dumper (this fork, any flavour) on the two outputs with the stock config.json and put the result in `<dumpdir>/sdk`; the ELF carries its base, so there is no dump-address prompt. |
| `il2live.py <dumpdir> "<path>" [--host IP] [--set V]` | reads / writes a value by a path that starts at a static field. Without `--host` it resolves against the dump (offline check), with `--host` live. `--find mana` lists every number/bool field reachable from a static field whose name, parent object/struct name or dictionary key contains the word (`CurrentStats{Type=SpellManaCurrent}.baseValue`), `--find 50` every field with that value; `--depth` hops, default 7 (a few seconds on a dump). |
| `il2diff.py <dumpdir> a.json b.json --eq 50 77` | two dumps of one session, value before and after: every matching address, walked back to a static field and printed as an il2live path. |
| `il2cheat.py <dumpdir> out.TLH "Name=path=value" ...` | TLH trainer from il2live paths: one StartUP injection on an `Update()` of a game class (auto-picked, `--hook Class` to choose), per cheat a flag and a value cell; every path is resolved from its static root on every frame through the il2cpp TypeInfo table, so the trainer survives restarts. `--check path` prints the hops and compares them with il2live against the dump. Needs capstone. |
| `il2diff.py <dumpdir> a.json b.json --changed [--class Name] [--same c.json]` | no value needed: every int / float / bool / enum field of a game object that differs between the dumps, then paths for the first hits. `--same` is a third dump of the unchanged state that filters moving values. |

Path syntax, passed through GUIs unchanged:

```
Class::field            static field of Class (root); namespace optional: Ns.Class::field, nested classes Outer.Inner
.field                  instance field, base class fields included
[i]                     element i of an array or List<T>
{42} {text}             Dictionary entry by int or string key
{Type=HealthCurrent}    Dictionary<System.Type, ...> entry by the type it stands for
{:ManaCaster}           Dictionary<int, SomeClass> entry by the class of its value (type caches: their int keys are hash codes that change per session)
{_guid=...} {name=...}  Dictionary entry by an identifier field of the key object
{#3}                    Dictionary entry by index (last resort)
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

Trainer notes: the hook entry uses `Section-Name` `Il2CppUserAssemblies.prx` with `Section-Protection` 5 (text segment, AOB unique inside it; uTrainer/Phoenix tags, the cheat menu PRX reads them too) and
`ModuleBase+offset` symbols for the TypeInfo table and the metadata pointer, loaded with `mov rax, Symbol` because the
module sits above 4 GB. Dictionary hops with int keys, `{Type=X}` keys and `{:Class}` keys are matched at runtime
(an int key of a `Dictionary<int, SomeClass>` is turned into `{:Class}` when that class is unique in the dictionary,
because such keys are per-session hash codes), `{_guid=...}` and string keys use the entry index seen in the dump
(entry order only changes when something is removed from the dictionary). Flag/Val cells are GetMem cells addressed
as `[Flag1]`, like the Unreal trainers.

Notes measured on real dumps (metadata v29 / v31, x64):

* object header 0x10 (`klass*`, `monitor*`); dump.cs class field offsets include it, struct offsets do not
* `Il2CppClass`: name 0x10, namespace 0x18, declaringType 0x50, parent 0x58, static_fields 0xB8
* arrays: elements from 0x20; `List<T>`: `_items` 0x10, `_size` 0x18; `Dictionary<K,V>`: `_entries` 0x18, `_count` 0x20, entry = {int hash, int next, key @8, value @0x10}
* static roots and classes are resolved in the running process through the il2cpp TypeInfo table, so the dump may come from an earlier session of the same build; instance addresses in `--eq`/`--changed` output are only valid for the session the dumps came from
* the first run on a dump builds `<dump>.bin.klasses.json` (about a minute), later runs take seconds
* values shown on screen are not always the stored ones (a marker counter showed 5 while the list had 11 entries): when `--eq` finds nothing, use `--find` by name or `--changed`
