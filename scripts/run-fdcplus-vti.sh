#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
TARGET_DIR="$ROOT/build/z80pack-upstream/targets100sim"
TARGET_BIN="$TARGET_DIR/targetsim"

FDCPLUS0=""
FDCPLUS1=""
FDCPLUS2=""
FDCPLUS3=""
FDCPLUS_TRACE=0
FDCPLUS_WRITE=0
FP_PORT=00
FP_FILE=""
CPU_MHZ=4

for arg in "$@"; do
    case "$arg" in
        FDCPLUS0=*) FDCPLUS0=${arg#*=} ;;
        FDCPLUS1=*) FDCPLUS1=${arg#*=} ;;
        FDCPLUS2=*) FDCPLUS2=${arg#*=} ;;
        FDCPLUS3=*) FDCPLUS3=${arg#*=} ;;
        FDCPLUS_TRACE=*) FDCPLUS_TRACE=${arg#*=} ;;
        FDCPLUS_WRITE=*) FDCPLUS_WRITE=${arg#*=} ;;
        FP_PORT=*) FP_PORT=${arg#*=} ;;
        FP_FILE=*) FP_FILE=${arg#*=} ;;
        CPU_MHZ=*) CPU_MHZ=${arg#*=} ;;
        DSI0=*|DSI1=*|DSI_TRACE=*|DSI_WRITE=*|DSI_BOOTSTRAP=*|IDE_TRACE=*) ;;
        *) echo "error: unsupported FDC+/VTI launch argument: $arg" >&2; exit 2 ;;
    esac
done

if [[ -z "$FDCPLUS0" || ! -f "$FDCPLUS0" ]]; then
    echo 'error: FDC+ VTI profile requires FDCPLUS0=<62K CP/M IBM-3740 image>' >&2
    exit 2
fi

size=$(stat -c %s "$FDCPLUS0")
if [[ "$size" != 256256 ]]; then
    echo "error: FDCPLUS0 must be a 256256-byte 77x26x128 IBM-3740 image (got $size)" >&2
    exit 2
fi

# This profile is still under active emulator development. Prepare the target
# overlay explicitly so changes to the VTI/bootstrap sources cannot be hidden
# behind the normal incremental-build stamp.
bash "$ROOT/scripts/prepare-targetsim.sh" >/dev/null
make -C "$TARGET_DIR/srcsim" FRONTPANEL=NO INFOPANEL=NO build >/dev/null

mkdir -p "$ROOT/build"
VTI_SCREEN="$ROOT/build/vti-screen.bin"
VTI_KBD="$ROOT/build/vti-kbd"

export TARGET_CONSOLE=cio
export TARGET_HEADTEST_ENABLE=0
export TARGET_FDCPLUS0="$(realpath "$FDCPLUS0")"
export TARGET_FDCPLUS_TRACE="$FDCPLUS_TRACE"
export TARGET_FDCPLUS_WRITE="$FDCPLUS_WRITE"
export TARGET_FDCPLUS_CPM_BOOTSTRAP=1
# MOVCPM 62 * layout: CCP DE00H, BDOS E600H, BIOS F400H-F77FH.
export TARGET_FDCPLUS_CPM_LOAD=0xde00
export TARGET_VTI_ENABLE=1
export TARGET_VTI_BASE=0xfc00
export TARGET_VTI_SCREEN="$VTI_SCREEN"
export TARGET_VTI_KBD="$VTI_KBD"
# VTI JMP2 -> S-100 VI2. The North Star ZPB supplies RST 2 on INTA.
export TARGET_VTI_VI=2
export TARGET_FP_PORT="$FP_PORT"
if [[ -n "$FP_FILE" ]]; then
    export TARGET_FP_FILE="$FP_FILE"
else
    unset TARGET_FP_FILE || true
fi

for pair in \
    "TARGET_FDCPLUS1=$FDCPLUS1" \
    "TARGET_FDCPLUS2=$FDCPLUS2" \
    "TARGET_FDCPLUS3=$FDCPLUS3"
do
    name=${pair%%=*}
    value=${pair#*=}
    if [[ -n "$value" && -f "$value" ]]; then
        printf -v "$name" '%s' "$(realpath "$value")"
        export "$name"
    else
        unset "$name" || true
    fi
done

unset TARGET_CF0 TARGET_CF1 TARGET_DSI0 TARGET_DSI1 TARGET_DSI_BOOTSTRAP || true

cd "$TARGET_DIR"
exec "$TARGET_BIN" -z -f "$CPU_MHZ" -c conf_3d/fdcplus-vti.conf
