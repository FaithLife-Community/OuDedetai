# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['scripts/run_app.py'],
    pathex=['.'],
    #binaries=[('/usr/bin/tclsh8.6', '.')],
    binaries=[],
    datas=[('ou_dedetai/img', 'img'),('ou_dedetai/assets', 'assets')],
    hiddenimports=["tkinter"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='oudedetai',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
