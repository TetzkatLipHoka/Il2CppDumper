@echo off
rem Builds the four release flavours into ..\Release:
rem   net10-win-x64 / net10-win-x86 : self-contained single file (like the upstream release zips)
rem   aot-win-x64   / aot-win-x86   : NativeAOT (needs Visual Studio C++ tools)
setlocal
set "PATH=%PATH%;C:\Program Files (x86)\Microsoft Visual Studio\Installer"
set VCVARS=C:\Program Files\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvarsall.bat
set OUT=%~dp0..\Release
cd /d "%~dp0"

for %%R in (win-x64 win-x86) do (
  echo === self-contained single file %%R
  dotnet publish Il2CppDumper\Il2CppDumper.csproj -c Release -f net10.0 -r %%R --self-contained -p:PublishSingleFile=true -p:PublishTrimmed=true -p:IncludeNativeLibrariesForSelfExtract=true -nologo -v q -o "%OUT%\net10-%%R" || exit /b 1
)

call :aot x64 win-x64 || exit /b 1
call :aot x86 win-x86 || exit /b 1
echo === done
exit /b 0

:aot
setlocal
echo === NativeAOT %2
call "%VCVARS%" %1 >nul
dotnet publish Il2CppDumper\Il2CppDumper.csproj -c Release -f net10.0 -r %2 -p:PublishAot=true -p:SelfContained=true -nologo -v q -o "%OUT%\aot-%2" || exit /b 1
del /q "%OUT%\aot-%2\*.pdb" 2>nul
endlocal
exit /b 0
