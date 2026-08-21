#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
BIN_DIR="${HOME}/.local/bin"
APP_DIR="${HOME}/.local/share/applications"
LAUNCHER="${BIN_DIR}/imsai-target-system"
DESKTOP="${APP_DIR}/com.peclark.z80pack-target-system.desktop"
APP_ID="com.peclark.z80pack-target-system"

mkdir -p "$BIN_DIR" "$APP_DIR"

if ! python3 -c 'import gi; gi.require_version("Gtk", "4.0"); gi.require_version("Vte", "3.91"); from gi.repository import Gtk, Vte' >/dev/null 2>&1; then
    cat >&2 <<'EOF'
GTK4/VTE Python bindings are not installed.
Install them with:

  sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-vte-3.91

or run:

  make gui-deps
EOF
    exit 2
fi

cat >"$LAUNCHER" <<EOF
#!/usr/bin/env bash
set -e
exec python3 "$ROOT/gui/app.py" "\$@"
EOF
chmod 0755 "$LAUNCHER"

cat >"$DESKTOP" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=IMSAI Target System
GenericName=S-100 Emulator
Comment=Run the IMSAI z80pack target-system emulator
Exec=$LAUNCHER
Icon=utilities-terminal
Terminal=false
Categories=Development;Emulator;
Keywords=IMSAI;S-100;CP/M;Z80;z80pack;emulator;
StartupNotify=true
StartupWMClass=$APP_ID
EOF
chmod 0644 "$DESKTOP"

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$APP_DIR" >/dev/null 2>&1 || true
fi

cat <<EOF
Installed IMSAI Target System GUI.

Application launcher:
  $DESKTOP

Command launcher:
  $LAUNCHER

Open Ubuntu's Applications view and search for "IMSAI Target System".
Right-click the application and choose "Add to Favorites" to pin it to the dock.

The desktop launcher points at this checkout:
  $ROOT
so future git pulls immediately update the installed application.
EOF
