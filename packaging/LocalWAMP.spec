# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files

project_root = Path(SPECPATH).parent
app_dir = project_root / 'app'


a = Analysis(
    [str(app_dir / 'main.py')],
    pathex=[str(app_dir)],
    binaries=[],
    datas=[(str(project_root / 'assets' / 'localwamp.ico'), 'assets')]
        + collect_data_files('customtkinter'),
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
    [],
    exclude_binaries=True,
    name='LocalWAMP',
    icon=str(project_root / 'assets' / 'localwamp.ico'),
    version=str(project_root / 'packaging' / 'version_info.txt'),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='LocalWAMP',
)
