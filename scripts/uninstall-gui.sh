#!/usr/bin/env bash
set -euo pipefail

BIN_DIR="${HOME}/.local/bin"
APP_DIR="${HOME}/.local/share/applications"
LAUNCHER="${BIN_DIR}/imsai-target-system"
DESKTOP="${APP_DIR}/com.peclark.z80pack-target-system.desktop"

rm -f "$LAUNCHER" "$DESKTOP"

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$APP_DIR" >/dev/null 2>&1 || true
fi

echo "Removed IMSAI Target System GUI launcher."
echo "Saved GUI settings under ~/.config/z80pack-target-system were left intact."
