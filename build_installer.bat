@echo off
setlocal enabledelayedexpansion

rem ---------------------------------------------------------------------
rem  build_installer.bat - Build the ImageMarker Windows installer
rem
rem  1. Checks that dist\ImageMarker.exe already exists (run build.bat
rem     first if it doesn't - this script does NOT build the exe itself).
rem  2. Locates the Inno Setup 6 or 7 compiler (ISCC.exe).
rem  3. Compiles installer\ImageMarker.iss.
rem  4. Prints the path to the resulting setup exe.
rem ---------------------------------------------------------------------

set "SCRIPT_DIR=%~dp0"
set "EXE_PATH=%SCRIPT_DIR%dist\ImageMarker.exe"
set "ISS_PATH=%SCRIPT_DIR%installer\ImageMarker.iss"

rem Read the version from the .iss so the reported path always matches
set "APP_VERSION="
for /f tokens^=2^ delims^=^" %%v in ('findstr /c:"#define MyAppVersion" "%ISS_PATH%"') do set "APP_VERSION=%%v"
set "SETUP_EXE=%SCRIPT_DIR%dist\ImageMarker-Setup-%APP_VERSION%.exe"

pushd "%SCRIPT_DIR%" || (
    echo [build_installer.bat] ERROR: could not change to "%SCRIPT_DIR%"
    exit /b 1
)

if not exist "%EXE_PATH%" (
    echo [build_installer.bat] ERROR: "%EXE_PATH%" not found.
    echo [build_installer.bat] Run build.bat first to produce it, then re-run this script.
    popd
    exit /b 1
)

rem Prefer whatever ISCC.exe is on PATH, then the usual per-user and
rem machine-wide install locations of Inno Setup 6 and 7.
set "ISCC="
set "PF86=%ProgramFiles(x86)%"
for /f "delims=" %%p in ('where ISCC.exe 2^>nul') do if not defined ISCC set "ISCC=%%p"
for %%v in (7 6) do (
    if not defined ISCC if exist "%LocalAppData%\Programs\Inno Setup %%v\ISCC.exe" set "ISCC=%LocalAppData%\Programs\Inno Setup %%v\ISCC.exe"
    if not defined ISCC if exist "%ProgramFiles%\Inno Setup %%v\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup %%v\ISCC.exe"
    if not defined ISCC if exist "%PF86%\Inno Setup %%v\ISCC.exe" set "ISCC=%PF86%\Inno Setup %%v\ISCC.exe"
)
if not defined ISCC (
    echo [build_installer.bat] ERROR: could not find ISCC.exe ^(Inno Setup 6 or 7 compiler^).
    echo [build_installer.bat] Install Inno Setup from https://jrsoftware.org/isdl.php
    popd
    exit /b 1
)

echo [build_installer.bat] Using compiler: "%ISCC%"
echo [build_installer.bat] Compiling "%ISS_PATH%"...
"%ISCC%" "%ISS_PATH%"
if errorlevel 1 (
    echo [build_installer.bat] ERROR: Inno Setup compilation failed.
    popd
    exit /b 1
)

if exist "%SETUP_EXE%" (
    echo.
    echo [build_installer.bat] Build succeeded:
    echo   "%SETUP_EXE%"
) else (
    echo.
    echo [build_installer.bat] WARNING: build finished but "%SETUP_EXE%" was not found.
)

popd
endlocal
