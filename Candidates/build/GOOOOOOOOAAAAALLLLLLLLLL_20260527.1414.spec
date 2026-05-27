# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['c:\\Users\\akuzub\\One Diversified\\Data Driven Design Team - kuzub\\Infocom - Goal To Colour\\main.py'],
    pathex=[],
    binaries=[],
    datas=[('c:\\Users\\akuzub\\One Diversified\\Data Driven Design Team - kuzub\\Infocom - Goal To Colour\\assets\\countries.json', 'assets'), ('c:\\Users\\akuzub\\One Diversified\\Data Driven Design Team - kuzub\\Infocom - Goal To Colour\\assets\\patterns.json', 'assets'), ('c:\\Users\\akuzub\\One Diversified\\Data Driven Design Team - kuzub\\Infocom - Goal To Colour\\assets\\Version.json', 'assets'), ('c:\\Users\\akuzub\\One Diversified\\Data Driven Design Team - kuzub\\Infocom - Goal To Colour\\assets\\worldcup_teams.json', 'assets'), ('c:\\Users\\akuzub\\One Diversified\\Data Driven Design Team - kuzub\\Infocom - Goal To Colour\\README.md', '.')],
    hiddenimports=[],
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
    name='GOOOOOOOOAAAAALLLLLLLLLL_20260527.1414',
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
