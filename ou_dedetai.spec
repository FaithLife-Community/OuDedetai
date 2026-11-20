# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['scripts/run_app.py'],
    pathex=[],
    #binaries=[('/usr/bin/tclsh8.6', '.')],
    binaries=[],
    datas=[('ou_dedetai/img', 'img'),('ou_dedetai/assets', 'assets')],
    hiddenimports=["PySide6.QtWidgets"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter"],
    noarchive=False,
)

# Leave out Qt parts Ou Dedetai never uses (#577). The virtual keyboard input plugin
# alone pulls in Qt Quick and QML, and the PDF image plugin Qt Pdf: together ~30 MB.
# Desktops bring their own on-screen keyboards through the input method plugins we keep.
_unused_qt = (
    "PySide6/Qt/plugins/platforminputcontexts/libqtvirtualkeyboardplugin",
    "PySide6/Qt/plugins/imageformats/libqpdf",
    "PySide6/Qt/plugins/imageformats/libqtiff",
    "PySide6/Qt/plugins/imageformats/libqwebp",
    "PySide6/Qt/plugins/imageformats/libqicns",
    "PySide6/Qt/plugins/imageformats/libqtga",
    "PySide6/Qt/plugins/imageformats/libqwbmp",
    # Displays without X11 or Wayland (framebuffer, VNC, EGL full screen).
    "PySide6/Qt/plugins/platforms/libqlinuxfb",
    "PySide6/Qt/plugins/platforms/libqvnc",
    "PySide6/Qt/plugins/platforms/libqvkkhrdisplay",
    "PySide6/Qt/plugins/platforms/libqeglfs",
    "PySide6/Qt/plugins/platforms/libqminimalegl",
    "PySide6/Qt/plugins/egldeviceintegrations/",
    "PySide6/Qt/lib/libQt6Quick",
    "PySide6/Qt/lib/libQt6Qml",
    "PySide6/Qt/lib/libQt6VirtualKeyboard",
    "PySide6/Qt/lib/libQt6Pdf",
)


def _used(entry):
    name = entry[0]
    if name.startswith(_unused_qt):
        return False
    if entry[2] == "SYMLINK" and str(entry[1]).startswith(_unused_qt):
        return False  # a link (e.g. libQt6Quick.so.6) to a library left out
    # Qt's own translations: only the base ones (dialog buttons etc.) are used.
    if name.startswith("PySide6/Qt/translations/") and not name.split("/")[-1].startswith("qtbase_"):
        return False
    return True


a.binaries = [b for b in a.binaries if _used(b)]
a.datas = [d for d in a.datas if _used(d)]
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
