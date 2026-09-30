# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for ImageMarker.
#
# Build with:
#   pyinstaller ImageMarker.spec
# (or just run build.bat, which sets up a venv and does this for you)
#
# This is a single-file build: passing a.binaries/a.datas directly into EXE()
# (instead of a separate COLLECT() step) bundles everything into one
# executable, produced at dist/ImageMarker.exe

from PyInstaller.utils.hooks import collect_submodules

hidden_imports = collect_submodules("imagemarker")

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[("assets/icon.ico", "assets")],  # window icon (see app._icon_path)
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="ImageMarker",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/icon.ico",
)
