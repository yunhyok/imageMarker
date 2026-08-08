@echo off
setlocal enabledelayedexpansion

rem ---------------------------------------------------------------------
rem  build_installer.bat - Build the ImageMarker Windows installer
rem
rem  1. Checks that dist\ImageMarker.exe already exists (run build.bat
rem     first if it doesn't - this script does NOT build the exe itself).
rem  2. Locates the Inno Setup 6 compiler (ISCC.exe).
rem  3. Compiles installer\ImageMarker.iss.
rem  4. Prints the path to the resulting setup exe.
rem ---------------------------------------------------------------------

set "SCRIPT_DIR=%~dp0"
set "EXE_PATH=%SCRIPT_DIR%dist\ImageMarker.exe"
set "ISS_PATH=%SCRIPT_DIR%installer\ImageMarker.iss"
set "SETUP_EXE=%SCRIPT_DIR%dist\ImageMarker-Setup-1.0.0.exe"

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

set "ISCC=C:\Users\yunhy\AppData\Local\Programs\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" (
    set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
)
if not exist "%ISCC%" (
    echo [build_installer.bat] ERROR: could not find ISCC.exe ^(Inno Setup 6 compiler^).
    echo [build_installer.bat] Install Inno Setup 6 from https://jrsoftware.org/isdl.php
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
