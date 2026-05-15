# -*- mode: python ; coding: utf-8 -*-

import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules


project_root = os.path.abspath(os.path.join(SPECPATH, ".."))


def safe_collect_data_files(package):
    try:
        return collect_data_files(package)
    except Exception:
        return []


def safe_collect_submodules(package):
    try:
        return collect_submodules(package)
    except Exception:
        return []


datas = [
    (os.path.join(project_root, "app.py"), "."),
    (os.path.join(project_root, "watermark.py"), "."),
    (os.path.join(project_root, "presets.py"), "."),
    (os.path.join(project_root, "gdrive.py"), "."),
    (os.path.join(project_root, "requirements.txt"), "."),
]

for package in [
    "streamlit",
    "altair",
    "faster_whisper",
    "google_auth_oauthlib",
    "googleapiclient",
]:
    datas += safe_collect_data_files(package)

hiddenimports = []
for package in [
    "streamlit",
    "pandas",
    "PIL",
    "google",
    "google_auth_oauthlib",
    "googleapiclient",
    "openai",
    "faster_whisper",
    "ctranslate2",
    "tokenizers",
    "av",
    "send2trash",
]:
    hiddenimports += safe_collect_submodules(package)


a = Analysis(
    [os.path.join(project_root, "start.py")],
    pathex=[project_root],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
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
    name="ReelsWatermarkTool",
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
    name="ReelsWatermarkTool",
)
