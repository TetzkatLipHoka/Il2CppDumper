# Il2CppDumper

[![Build status](https://ci.appveyor.com/api/projects/status/anhqw33vcpmp8ofa?svg=true)](https://ci.appveyor.com/project/Perfare/il2cppdumper/branch/master/artifacts)

中文说明请戳[这里](README.zh-CN.md)

Unity il2cpp reverse engineer

## Features

* Complete DLL restore (except code), can be used to extract `MonoBehaviour` and `MonoScript`
* Supports ELF, ELF64, Mach-O, PE, NSO and WASM format
* Supports Unity 5.3 - 2022.2
* Supports generate IDA, Ghidra and Binary Ninja scripts to help them better analyze il2cpp files
* Supports generate structures header file
* Supports Android memory dumped `libil2cpp.so` file to bypass protection
* Support bypassing simple PE protection

## Usage

Run `Il2CppDumper.exe` and choose the il2cpp executable file and `global-metadata.dat` file, then enter the information as prompted

The program will then generate all the output files in current working directory

### PlayStation 4 / 5 (this fork)

Decrypted PS4/PS5 `Il2CppUserAssemblies.prx` (ELF `e_type` 0xFE18, no section headers) is loaded directly:

* PS4 `DT_SCE_RELA` relocations and `DT_SCE_SYMTAB` are read from `PT_SCE_DYNLIBDATA`; PS5 uses the standard tags.
* The "dump file" prompt and the ".init_proc protected" warning are skipped for these files.
* `Il2CppTypeDefinitionSizes` living in the read-only code segment no longer make the `MetadataRegistration` search fail.
* Fake-signed SELF (`4F 15 3D 1D`, output of make_fself) is unwrapped in memory, no unfself step needed.
* `ps4tools/il2mem.py` pulls `global-metadata.dat` and a loadable image of the module out of a ps4debug memory dump
  (`ps4dump.py` from ps4-unreal-dumper), so a running game is enough: no prx/metadata files, no decryption.
  Run the dumper on the two outputs with `NoRedirectedPointer: true` and the printed base as dump address.
* `ps4tools/il2live.py` reads or writes a value in the running game by a path that starts at a static field, e.g.
  `GameStateManager::_instance._mainCharacterEntity.componentCache{611004928}.manas[0]._currentManaStatObject.baseValue`
  (`::` static root, `.field`, `[i]` array/List element, `{key}` Dictionary lookup, `:Class` downcast, real classes are
  read from the object headers). Without `--host` it resolves against the memory dump, so paths can be checked offline;
  `--find word|value` lists paths from every static field. Needs numpy, live access needs the `ps4debug` module.
* `ps4tools/il2diff.py` compares two dumps of one game session (`--eq 50 77`: value before and after) and turns every
  hit into an il2live path by walking the object references back to a static field, verified against both dumps.
* When LTO folded `Il2CppCodeRegistration` into code (seen in Blasphemous 2), it is reconstructed from the
  code gen module table, the generic method pointer table and the invoker table (`Utils/LtoSearch.cs`).

## Command-line

```
Il2CppDumper.exe <executable-file> <global-metadata> <output-directory>
```

### Outputs

#### DummyDll

Folder, containing all restored dll files

Use [dnSpy](https://github.com/0xd4d/dnSpy), [ILSpy](https://github.com/icsharpcode/ILSpy) or other .Net decompiler tools to view

Can be used to extract Unity `MonoBehaviour` and `MonoScript`, for [UtinyRipper](https://github.com/mafaca/UtinyRipper), [UABE](https://7daystodie.com/forums/showthread.php?22675-Unity-Assets-Bundle-Extractor)

#### ida.py

For IDA

#### ida_with_struct.py

For IDA, read il2cpp.h file and apply structure information in IDA

#### il2cpp.h

structure information header file

#### ghidra.py

For Ghidra

#### Il2CppBinaryNinja

For BinaryNinja

#### ghidra_wasm.py

For Ghidra, work with [ghidra-wasm-plugin](https://github.com/nneonneo/ghidra-wasm-plugin)

#### script.json

For ida.py, ghidra.py and Il2CppBinaryNinja

#### stringliteral.json

Contains all stringLiteral information

### Configuration

All the configuration options are located in `config.json`

Available options:

* `DumpMethod`, `DumpField`, `DumpProperty`, `DumpAttribute`, `DumpFieldOffset`, `DumpMethodOffset`, `DumpTypeDefIndex`
  * Whether to output these information to dump.cs

* `GenerateDummyDll`, `GenerateScript`
  * Whether to generate these things

* `DummyDllAddToken`
  * Whether to add token in DummyDll

* `RequireAnyKey`
  * Whether to press any key to exit at the end

* `ForceIl2CppVersion`, `ForceVersion`
  * If `ForceIl2CppVersion` is `true`, the program will use the version number specified in `ForceVersion` to choose parser for il2cpp binaries (does not affect the choice of metadata parser). This may be useful on some older il2cpp version (e.g. the program may need to use v16 parser on il2cpp v20 (Android) binaries in order to work properly)

* `ForceDump`
  * Force files to be treated as dumped

* `NoRedirectedPointer`
  * Treat pointers in dumped files as unredirected, This option needs to be `true` for files dumped from some devices
* `NoPELoader`
  * On Windows the dumper falls back to a "custom PE loader" when the static search finds nothing: it loads the
    file with `LoadLibrary`, which runs the file's own startup code inside the dumper. `true` forbids that; use it
    for files you do not trust. Protected files whose code and data are still plain text (Denuvo: sections renamed,
    `.data` flagged `0xC0000020`) no longer need the loader: sections are classified by their memory flags.

## Common errors

#### `ERROR: Metadata file supplied is not valid metadata file.`  

Make sure you choose the correct file. Sometimes games may obfuscate this file for content protection purposes and so on. Deobfuscating of such files is beyond the scope of this program, so please **DO NOT** file an issue regarding to deobfuscating.

If your file is `libil2cpp.so` and you have a rooted Android phone, you can try my other project [Zygisk-Il2CppDumper](https://github.com/Perfare/Zygisk-Il2CppDumper), it can bypass this protection.

#### `ERROR: Can't use auto mode to process file, try manual mode.`

Please note that the executable file for the PC platform is `GameAssembly.dll` or `*Assembly.dll`

You can open a new issue and upload the file, I will try to solve.

#### `ERROR: This file may be protected.`

Il2CppDumper detected that the executable file has been protected, use `GameGuardian` to dump `libil2cpp.so` from the game memory, then use Il2CppDumper to load and follow the prompts, can bypass most protections.

If you have a rooted Android phone, you can try my other project [Zygisk-Il2CppDumper](https://github.com/Perfare/Zygisk-Il2CppDumper), it can bypass almost all protections.

## Credits

- Jumboperson - [Il2CppDumper](https://github.com/Jumboperson/Il2CppDumper)
