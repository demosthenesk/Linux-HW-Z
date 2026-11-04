#!/bin/bash
# Build Linux-HW-Z-<version>-x86_64.AppImage on Ubuntu 24.04.
#
# Bundles: a pruned PySide6 6.8.1 (Qt Core/Gui/Widgets/DBus/Svg + xcb/wayland platform plugins),
# the xcb helper libraries the Qt xcb plugin needs, pci.ids, and libhwz.so (CPUID + benchmark).
# Uses the host's /usr/bin/python3 (3.12 on Ubuntu 24.04; any 3.9+ works).
#
# Needs: python3.12-venv, gcc, curl, libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1
#        libxcb-render-util0 libxkbcommon-x11-0, hwdata (pci.ids)
set -euo pipefail

SRC="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="$(python3 -c "import sys; sys.path.insert(0,'$SRC'); import hwz; print(hwz.__version__)")"
BUILD="${BUILD_DIR:-$SRC/build}"
APPDIR="$BUILD/AppDir"
OUT="${OUT_DIR:-$SRC/dist}"
PYSIDE_VERSION=6.8.1
NAME="Linux-HW-Z-$VERSION-x86_64.AppImage"

echo "== Linux HW-Z $VERSION"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/share/linux-hw-z" "$APPDIR/usr/lib/python3/site-packages" "$APPDIR/usr/lib" "$OUT"

# ---- native library
gcc -O2 -march=x86-64 -mtune=generic -fPIC -shared -fvisibility=hidden \
    -o "$SRC/hwz/native/libhwz.so" "$SRC/hwz/native/libhwz.c"

# ---- application
rsync -a --delete --exclude '__pycache__' --exclude '*.pyc' "$SRC/hwz" "$APPDIR/usr/share/linux-hw-z/"
for ids in /usr/share/misc/pci.ids /usr/share/hwdata/pci.ids; do
    [ -f "$ids" ] && cp "$ids" "$APPDIR/usr/share/linux-hw-z/hwz/data/pci.ids" && break
done
cat > "$APPDIR/usr/share/linux-hw-z/launcher.py" <<'EOF'
import os
import sys

here = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [here, os.path.normpath(os.path.join(here, "..", "..", "lib", "python3", "site-packages"))]
from hwz.__main__ import main  # noqa: E402

sys.exit(main())
EOF

# ---- PySide6 (pruned)
VENV="$BUILD/venv"
if [ ! -x "$VENV/bin/pip" ]; then
    python3.12 -m venv "$VENV"
fi
"$VENV/bin/pip" install -q "PySide6-Essentials==$PYSIDE_VERSION"
SP="$("$VENV/bin/python" -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')"
DST="$APPDIR/usr/lib/python3/site-packages"
cp -a "$SP/shiboken6" "$DST/"
mkdir -p "$DST/PySide6/Qt/lib" "$DST/PySide6/Qt/plugins"
P="$SP/PySide6"
cp -a "$P/__init__.py" "$P/_config.py" "$P/_git_pyside_version.py" "$DST/PySide6/" 2>/dev/null || true
cp -a "$P"/libpyside6.abi3.so* "$DST/PySide6/"
for m in QtCore QtGui QtWidgets; do cp -a "$P/$m.abi3.so" "$DST/PySide6/"; done
for l in Core Gui Widgets DBus XcbQpa WaylandClient WaylandEglClientHwIntegration Svg OpenGL; do
    cp -a "$P/Qt/lib/libQt6$l.so"* "$DST/PySide6/Qt/lib/"
done
cp -a "$P"/Qt/lib/libicu*.so* "$DST/PySide6/Qt/lib/"
PL="$P/Qt/plugins"
copy_plugin() { mkdir -p "$DST/PySide6/Qt/plugins/$1"; cp -a "$PL/$1/"$2 "$DST/PySide6/Qt/plugins/$1/"; }
copy_plugin platforms libqxcb.so
copy_plugin platforms libqoffscreen.so
copy_plugin platforms 'libqwayland*.so'
for d in xcbglintegrations wayland-decoration-client wayland-graphics-integration-client \
         wayland-shell-integration platforminputcontexts; do
    [ -d "$PL/$d" ] && copy_plugin "$d" '*'
done
rm -f "$DST/PySide6/Qt/plugins/platforminputcontexts/libqtvirtualkeyboardplugin.so" \
      "$DST/PySide6/Qt/plugins/wayland-shell-integration/libwl-shell-plugin.so"
copy_plugin imageformats libqsvg.so
copy_plugin iconengines libqsvgicon.so
for t in libqgtk3.so libqxdgdesktopportal.so; do [ -f "$PL/platformthemes/$t" ] && copy_plugin platformthemes "$t"; done
cat > "$DST/PySide6/Qt/qt.conf" <<'EOF'
[Paths]
Prefix = .
EOF

# ---- xcb helper libraries (libxcb-cursor0 is missing on many Ubuntu installs)
for lib in libxcb-cursor.so.0 libxcb-icccm.so.4 libxcb-image.so.0 libxcb-keysyms.so.1 \
           libxcb-render-util.so.0 libxcb-util.so.1 libxkbcommon-x11.so.0; do
    f="$(ls /usr/lib/x86_64-linux-gnu/$lib* 2>/dev/null | head -1 || true)"
    if [ -n "$f" ]; then cp -L "$f" "$APPDIR/usr/lib/$lib"; else echo "warning: $lib not found on build host"; fi
done

# ---- desktop integration
cp "$SRC/hwz/data/linux-hw-z.svg" "$APPDIR/linux-hw-z.svg"
rsvg-convert -w 256 -h 256 "$SRC/hwz/data/linux-hw-z.svg" -o "$APPDIR/linux-hw-z.png"
cp "$APPDIR/linux-hw-z.png" "$APPDIR/.DirIcon"
mkdir -p "$APPDIR/usr/share/icons/hicolor/scalable/apps"
cp "$SRC/hwz/data/linux-hw-z.svg" "$APPDIR/usr/share/icons/hicolor/scalable/apps/"
cat > "$APPDIR/linux-hw-z.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Linux HW-Z
GenericName=System Information
Comment=CPU, mainboard, memory and graphics card information (CPU-Z + GPU-Z style)
Exec=linux-hw-z %U
Icon=linux-hw-z
Terminal=false
Categories=System;Monitor;Utility;
Keywords=cpu;gpu;hardware;sensors;benchmark;spd;memory;
X-AppImage-Version=$VERSION
EOF
mkdir -p "$APPDIR/usr/share/applications"
cp "$APPDIR/linux-hw-z.desktop" "$APPDIR/usr/share/applications/"
cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
PY=""
for p in /usr/bin/python3 /bin/python3 /usr/local/bin/python3; do
    if [ -x "$p" ] && "$p" -c 'import sys; sys.exit(sys.version_info < (3, 9))' 2>/dev/null; then PY="$p"; break; fi
done
if [ -z "$PY" ]; then
    msg="Linux HW-Z needs Python 3.9 or newer (/usr/bin/python3)."
    command -v zenity >/dev/null && zenity --error --text="$msg" 2>/dev/null || echo "$msg" >&2
    exit 1
fi
export LD_LIBRARY_PATH="$HERE/usr/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export QT_QPA_PLATFORMTHEME="${QT_QPA_PLATFORMTHEME:-xdgdesktopportal}"
exec "$PY" -s "$HERE/usr/share/linux-hw-z/launcher.py" "$@"
EOF
chmod +x "$APPDIR/AppRun"

# ---- check that every bundled shared object resolves
missing=0
while IFS= read -r so; do
    out="$(LD_LIBRARY_PATH="$APPDIR/usr/lib:$DST/PySide6/Qt/lib:$DST/PySide6:$DST/shiboken6" ldd "$so" 2>/dev/null | grep 'not found' || true)"
    if [ -n "$out" ]; then echo "unresolved in $so:"; echo "$out"; missing=1; fi
done < <(find "$APPDIR" -name '*.so*' -type f)
[ "$missing" = 0 ] || echo "warning: some libraries are expected from the host (see above)"

# ---- appimagetool
TOOL="$BUILD/appimagetool-x86_64.AppImage"
if [ ! -x "$TOOL" ]; then
    curl -fsSL -o "$TOOL" https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
    chmod +x "$TOOL"
fi
ARCH=x86_64 "$TOOL" --appimage-extract-and-run --comp zstd -n "$APPDIR" "$OUT/$NAME" >/dev/null
( cd "$OUT" && sha256sum "$NAME" > "$NAME.sha256" )
ls -la "$OUT/$NAME"
cat "$OUT/$NAME.sha256"
