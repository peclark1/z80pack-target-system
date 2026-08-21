#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
UPSTREAM="$ROOT/build/z80pack-upstream"
TARGET="$UPSTREAM/targets100sim"

bash "$ROOT/scripts/bootstrap-z80pack.sh" >/dev/null

rm -rf "$TARGET"
cp -a "$UPSTREAM/imsaisim" "$TARGET"

# Give the generated machine its own binary/name while continuing to reuse the
# mature IMSAI memory/config/control implementation from the pinned upstream.
sed -i 's/^MACHINE = imsai$/MACHINE = target/' "$TARGET/srcsim/Makefile"
sed -i 's/^MACHINE_SRCS = simcfg.c simio.c simmem.c simctl.c$/MACHINE_SRCS = simcfg.c simio.c simmem.c simctl.c target-ide.c/' "$TARGET/srcsim/Makefile"
sed -i 's/^#define DEF_CPU I8080/#define DEF_CPU Z80/' "$TARGET/srcsim/sim.h"
sed -i 's/^#define CPU_SPEED 2/#define CPU_SPEED 4/' "$TARGET/srcsim/sim.h"
sed -i 's/^#define MACHINE "imsai"/#define MACHINE "target"/' "$TARGET/srcsim/sim.h"
sed -i 's/IMSAI 8080 Simulation/IMSAI Target System Simulation/' "$TARGET/srcsim/sim.h"

# Replace the machine-specific I/O dispatch and add target-only devices.
cp "$ROOT/emulator/srcsim/simio.c" "$TARGET/srcsim/simio.c"
cp "$ROOT/emulator/srcsim/target-ide.c" "$TARGET/srcsim/target-ide.c"
cp "$ROOT/emulator/srcsim/target-ide.h" "$TARGET/srcsim/target-ide.h"

# Keep a copy with the generated machine for convenient manual launches.
cp "$ROOT/emulator/conf/system.conf" "$TARGET/conf_3d/system.conf"

echo "prepared target machine at $TARGET"
