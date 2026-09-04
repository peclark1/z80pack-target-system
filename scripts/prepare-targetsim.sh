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
sed -i 's/^MACHINE_SRCS = simcfg.c simio.c simmem.c simctl.c$/MACHINE_SRCS = simcfg.c simio.c simmem.c simctl.c target-ide.c target-dsi-fdc1.c target-fdcplus-type8.c target-fdcplus-bootstrap.c target-serialio-usb.c target-vti.c/' "$TARGET/srcsim/Makefile"
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
cp "$ROOT/emulator/srcsim/target-fdcplus-bootstrap.c" "$TARGET/srcsim/target-fdcplus-bootstrap.c"
cp "$ROOT/emulator/srcsim/target-fdcplus-bootstrap.h" "$TARGET/srcsim/target-fdcplus-bootstrap.h"
cp "$ROOT/emulator/srcsim/target-serialio-usb.c" "$TARGET/srcsim/target-serialio-usb.c"
cp "$ROOT/emulator/srcsim/target-serialio-usb.h" "$TARGET/srcsim/target-serialio-usb.h"
cp "$ROOT/emulator/srcsim/target-vti.c" "$TARGET/srcsim/target-vti.c"
cp "$ROOT/emulator/srcsim/target-vti.h" "$TARGET/srcsim/target-vti.h"

# z80pack's port dispatch table is static. Expose the VTI keyboard ports used
# by the historical and dedicated profiles; target-vti.c itself returns FFH
# unless the corresponding framebuffer base is active. Also invoke the
# emulator-only CP/M system-track loader after FDC+ media have been attached.
python3 - "$TARGET/srcsim/simio.c" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")

include_anchor = '#include "target-fdcplus-type8.h"\n'
include_new = '#include "target-fdcplus-type8.h"\n#include "target-fdcplus-bootstrap.h"\n'
if include_new not in text:
    if include_anchor not in text:
        raise SystemExit("error: target simio.c no longer matches FDC+ bootstrap include anchor")
    text = text.replace(include_anchor, include_new, 1)

port_anchor = "    [0x7f] = target_dsi_fdc1_status_in,\n\n    /* Original disk-head test fixture status and A/D converter. */"
port_new = "    [0x7f] = target_dsi_fdc1_status_in,\n\n    /* Polymorphic VTI keyboard: port equals framebuffer high byte. */\n    [0x88] = target_vti_keyboard_88_in,\n    [0xf8] = target_vti_keyboard_f8_in,\n    [0xfc] = target_vti_keyboard_fc_in,\n\n    /* Original disk-head test fixture status and A/D converter. */"
if port_new not in text:
    if port_anchor not in text:
        raise SystemExit("error: target simio.c no longer matches VTI keyboard-port patch anchor")
    text = text.replace(port_anchor, port_new, 1)

init_anchor = "    target_fdcplus_type8_init();\n    target_serialio_usb_init();"
init_new = "    target_fdcplus_type8_init();\n    target_fdcplus_bootstrap_init();\n    target_serialio_usb_init();"
if init_new not in text:
    if init_anchor not in text:
        raise SystemExit("error: target simio.c no longer matches FDC+ bootstrap init anchor")
    text = text.replace(init_anchor, init_new, 1)

path.write_text(text, encoding="utf-8")
PY

# Keep target and compatibility configs with the generated machine for
# convenient manual launches.
cp "$ROOT/emulator/conf/system.conf" "$TARGET/conf_3d/system.conf"
cp "$ROOT/emulator/conf/dsi-compat.conf" "$TARGET/conf_3d/dsi-compat.conf"
cp "$ROOT/emulator/conf/fdcplus-vti.conf" "$TARGET/conf_3d/fdcplus-vti.conf"

echo "prepared target machine at $TARGET"
