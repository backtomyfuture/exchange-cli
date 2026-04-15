# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['npm/platforms/darwin-arm64/entrypoint.py'],
    pathex=['/Users/jarod/Documents/exchange-cli'],
    binaries=[],
    datas=[],
    hiddenimports=[
        'exchange_cli.commands.calendar',
        'exchange_cli.commands.config',
        'exchange_cli.commands.contact',
        'exchange_cli.commands.daemon',
        'exchange_cli.commands.draft',
        'exchange_cli.commands.email',
        'exchange_cli.commands.folder',
        'exchange_cli.commands.task',
        'markdownify',
        'bs4',
    ],
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
    name='exchange-cli',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
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
    upx=False,
    upx_exclude=[],
    name='exchange-cli',
)
