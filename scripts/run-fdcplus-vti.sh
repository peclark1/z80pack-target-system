#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
TARGET_DIR="$ROOT/build/z80pack-upstream/targets100sim"
TARGET_BIN="$TARGET_DIR/targetsim"
TARGET_PREPARED="$TARGET_DIR/.target-prepared"

FDCPLUS0=""
FDCPLUS1=""
FDCPLUS2=""
FDCPLUS3=""
FDCPLUS_TRACE=0
FDCPLUS_WRITE=1
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

# Work Copy uses metadata-preserving copies, so a copy made from a protected
# master image may inherit read-only mode bits. When writes are requested,
# make only emulator-managed work images under build/ owner-writable. Never
# change permissions on a master image selected from elsewhere.
if [[ "$FDCPLUS_WRITE" != 0 ]]; then
    for image in "$FDCPLUS0" "$FDCPLUS1" "$FDCPLUS2" "$FDCPLUS3"; do
        [[ -n "$image" && -f "$image" ]] || continue
        resolved=$(realpath "$image")
        case "$resolved" in
            "$ROOT"/build/*) chmod u+w "$resolved" ;;
        esac
        if [[ ! -w "$resolved" ]]; then
            echo "warning: FDC+ writes requested but image is not writable: $resolved" >&2
        fi
    done
fi

# Use the repository's dependency-tracked targetsim build. The dedicated VTI
# profile added a few overlay inputs after the original Makefile dependency
# list was created, so invalidate the preparation stamp only when one of those
# files is newer. With no source/config changes, Make is a no-op and Start is
# effectively immediate; after development changes it rebuilds once.
for source in \
    "$ROOT/emulator/conf/fdcplus-vti.conf" \
    "$ROOT/emulator/srcsim/target-fdcplus-bootstrap.c" \
    "$ROOT/emulator/srcsim/target-fdcplus-bootstrap.h"
do
    if [[ ! -e "$TARGET_PREPARED" || "$source" -nt "$TARGET_PREPARED" ]]; then
        rm -f "$TARGET_PREPARED"
        break
    fi
done
make -C "$ROOT" build >/dev/null

mkdir -p "$ROOT/build"
VTI_SCREEN="$ROOT/build/vti-screen.bin"
VTI_KBD="$ROOT/build/vti-kbd"

# Preserve every FDC+/VTI diagnostic/trace run on disk while still displaying
# it in the VTE terminal.  targetsim emits controller traces and unsupported
# command diagnostics on stderr, so teeing only stderr keeps the emulator's
# normal terminal/PTY semantics unchanged.  Keep timestamped history and a
# stable symlink for quick grep/open operations from the GUI.
LOG_DIR="$ROOT/build/logs"
mkdir -p "$LOG_DIR"
LOG_STAMP=$(date +%Y%m%d-%H%M%S)
TARGETSIM_LOG="$LOG_DIR/targetsim-$LOG_STAMP.log"
ln -sfn "$(basename "$TARGETSIM_LOG")" "$LOG_DIR/targetsim-latest.log"
exec 2> >(tee -a "$TARGETSIM_LOG" >&2)
echo "targetsim diagnostics log: $TARGETSIM_LOG" >&2

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
