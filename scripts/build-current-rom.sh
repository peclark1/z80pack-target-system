#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
ROM_SRC="$ROOT/build/target-rom-source"
ROM_URL="https://github.com/peclark1/s100-target-system-4k-master-rom.git"
ROM_COMMIT="a62e5ed4a021d93df0944113badd78b23e4030ab"

mkdir -p "$ROOT/build"

if [[ ! -d "$ROM_SRC/.git" ]]; then
    git clone "$ROM_URL" "$ROM_SRC"
fi

git -C "$ROM_SRC" fetch --quiet origin "$ROM_COMMIT"
git -C "$ROM_SRC" checkout --quiet --detach "$ROM_COMMIT"

make -C "$ROM_SRC" clean verify
python3 "$ROOT/tools/bin2ihex.py" \
    "$ROM_SRC/build/IMSAI_TARGET_MONITOR_4K.bin" \
    "$ROOT/build/target-monitor.hex"

actual=$(git -C "$ROM_SRC" rev-parse HEAD)
echo "target monitor ready: $ROOT/build/target-monitor.hex"
echo "ROM source revision: $actual"
