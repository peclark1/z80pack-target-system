#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
UPSTREAM="$ROOT/build/z80pack-upstream"
TARGET="$UPSTREAM/targets100sim"

bash "$ROOT/scripts/bootstrap-z80pack.sh" >/dev/null

# z80pack's IMSAI STDIO HAL reads one byte directly into an uninitialized int.
# On little-endian hosts the upper bytes can retain stack garbage, so a valid
# keypress may look like a negative result to hal_data_in(). SIO1A then returns
# its previous character; before the first successful receive that is 00H,
# which appears as ^@ on authentic DSI console software. Read into an actual
# byte instead. Keep this as a narrowly scoped local upstream fix until it is
# available in the pinned z80pack revision.
python3 - "$UPSTREAM/iodevices/imsai-hal.c" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
old = "static int stdio_in(void)\n{\n\tint data;\n\tstruct pollfd p[1];"
new = "static int stdio_in(void)\n{\n\tunsigned char data;\n\tstruct pollfd p[1];"
if old in text:
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
elif new not in text:
    raise SystemExit("error: pinned z80pack imsai-hal.c no longer matches the expected STDIO input routine")
PY

rm -rf "$TARGET"
cp -a "$UPSTREAM/imsaisim" "$TARGET"

# Give the generated machine its own binary/name while continuing to reuse the
# mature IMSAI memory/config/control implementation from the pinned upstream.
sed -i 's/^MACHINE = imsai$/MACHINE = target/' "$TARGET/srcsim/Makefile"
sed -i 's/^MACHINE_SRCS = simcfg.c simio.c simmem.c simctl.c$/MACHINE_SRCS = simcfg.c simio.c simmem.c simctl.c target-ide.c target-dsi-fdc1.c target-fdcplus-type8.c target-serialio-usb.c target-vti.c/' "$TARGET/srcsim/Makefile"
sed -i 's/^#define DEF_CPU I8080/#define DEF_CPU Z80/' "$TARGET/srcsim/sim.h"
sed -i 's/^#define CPU_SPEED 2/#define CPU_SPEED 4/' "$TARGET/srcsim/sim.h"
sed -i 's/^#define MACHINE "imsai"/#define MACHINE "target"/' "$TARGET/srcsim/sim.h"
sed -i 's/IMSAI 8080 Simulation/IMSAI Target System Simulation/' "$TARGET/srcsim/sim.h"

# The physical target currently has one CPU-visible 64K address space only.
# Keep upstream banked-ROM compile plumbing intact because shared IMSAI code
# expects R_flag to exist, but advertise no additional MMU RAM banks. Our
# target I/O map exposes no bank-select port, so those upstream storage arrays
# remain unreachable by target software.
sed -i 's/^int num_banks = sizeof(banks) \/ sizeof(BYTE \*) - 1;$/int num_banks = 0;/' "$TARGET/srcsim/simmem.c"

# Replace the machine-specific I/O dispatch and add target-only devices.
cp "$ROOT/emulator/srcsim/simio.c" "$TARGET/srcsim/simio.c"
cp "$ROOT/emulator/srcsim/target-ide.c" "$TARGET/srcsim/target-ide.c"
cp "$ROOT/emulator/srcsim/target-ide.h" "$TARGET/srcsim/target-ide.h"
cp "$ROOT/emulator/srcsim/target-dsi-fdc1.c" "$TARGET/srcsim/target-dsi-fdc1.c"
cp "$ROOT/emulator/srcsim/target-dsi-fdc1.h" "$TARGET/srcsim/target-dsi-fdc1.h"
cp "$ROOT/emulator/srcsim/target-fdcplus-type8.c" "$TARGET/srcsim/target-fdcplus-type8.c"
cp "$ROOT/emulator/srcsim/target-fdcplus-type8.h" "$TARGET/srcsim/target-fdcplus-type8.h"
cp "$ROOT/emulator/srcsim/target-serialio-usb.c" "$TARGET/srcsim/target-serialio-usb.c"
cp "$ROOT/emulator/srcsim/target-serialio-usb.h" "$TARGET/srcsim/target-serialio-usb.h"
cp "$ROOT/emulator/srcsim/target-vti.c" "$TARGET/srcsim/target-vti.c"
cp "$ROOT/emulator/srcsim/target-vti.h" "$TARGET/srcsim/target-vti.h"

# Keep target and historical DSI compatibility configs with the generated
# machine for convenient manual launches. The DSI+VTI profile uses the same
# 64K RAM configuration; the VTI device redirects F800H-FBFFH at runtime.
cp "$ROOT/emulator/conf/system.conf" "$TARGET/conf_3d/system.conf"
cp "$ROOT/emulator/conf/dsi-compat.conf" "$TARGET/conf_3d/dsi-compat.conf"

echo "prepared target machine at $TARGET"
