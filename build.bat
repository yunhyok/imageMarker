@echo off
setlocal enabledelayedexpansion

rem ---------------------------------------------------------------------
rem  build.bat - Build ImageMarker.exe with PyInstaller
rem
rem  1. Creates a .venv in this folder if one doesn't already exist.
rem  2. Installs requirements.txt + pyinstaller into it.
rem  3. Runs "pyinstaller ImageMarker.spec".
rem  4. Prints the path to the resulting exe.
rem
rem  Safe to re-run; re-uses the existing .venv if present.
rem ---------------------------------------------------------------------

set "SCRIPT_DIR=%~dp0"
set "VENV_DIR=%SCRIPT_DIR%.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"

pushd "%SCRIPT_DIR%" || (
    echo [build.bat] ERROR: could not change to "%SCRIPT_DIR%"
    exit /b 1
)

if not exist "%VENV_PY%" (
    echo [build.bat] Creating virtual environment in "%VENV_DIR%"...
    python -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo [build.bat] ERROR: failed to create virtual environment.
        popd
        exit /b 1
    )
) else (
    echo [build.bat] Using existing virtual environment "%VENV_DIR%".
)

echo [build.bat] Installing dependencies...
"%VENV_PY%" -m pip install --upgrade pip
if errorlevel 1 (
    echo [build.bat] ERROR: failed to upgrade pip.
    popd
    exit /b 1
)

"%VENV_PY%" -m pip install -r "%SCRIPT_DIR%requirements.txt" pyinstaller
if errorlevel 1 (
    echo [build.bat] ERROR: failed to install dependencies.
    popd
    exit /b 1
)

echo [build.bat] Running PyInstaller...
"%VENV_PY%" -m PyInstaller "%SCRIPT_DIR%ImageMarker.spec" --noconfirm
if errorlevel 1 (
    echo [build.bat] ERROR: PyInstaller build failed.
    popd
    exit /b 1
)

set "EXE_PATH=%SCRIPT_DIR%dist\ImageMarker.exe"

if exist "%EXE_PATH%" (
    echo.
    echo [build.bat] Build succeeded:
    echo   "%EXE_PATH%"
) else (
    echo.
    echo [build.bat] WARNING: build finished but "%EXE_PATH%" was not found.
)

popd
endlocal
