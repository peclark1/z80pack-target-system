PYTHON ?= python3
ROM_BIN ?=
ROM_HEX := build/target-monitor.hex
TARGET_DIR := build/z80pack-upstream/targets100sim
TARGET_BIN := $(TARGET_DIR)/targetsim
CF0 ?= disks/cf0.img
CF1 ?= disks/cf1.img
IDE_TRACE ?= 0
SMOKE_CF := build/smoke-cf0.img

.PHONY: help bootstrap prepare rom current-rom build run smoke-cf smoke test clean

help:
	@printf '%s\n' \
	  'make bootstrap                     Fetch pinned z80pack upstream' \
	  'make prepare                       Create target-machine source overlay' \
	  'make rom ROM_BIN=/path/monitor.bin Convert logical 4K ROM to Intel HEX' \
	  'make current-rom                   Build pinned target ROM project revision' \
	  'make build                         Build the targetsim emulator' \
	  'make run                           Run with disks/cf0.img and disks/cf1.img' \
	  'make run IDE_TRACE=1               Run with IDE command tracing enabled' \
	  'make smoke                         Real-ROM IDE boot regression' \
	  'make test                          Run host-side regression tests' \
	  'make clean                         Remove generated build output'

bootstrap:
	bash scripts/bootstrap-z80pack.sh

prepare:
	bash scripts/prepare-targetsim.sh

rom:
	@if [ -z "$(ROM_BIN)" ]; then \
		echo 'error: set ROM_BIN to IMSAI_TARGET_MONITOR_4K.bin' >&2; \
		exit 2; \
	fi
	$(PYTHON) tools/bin2ihex.py "$(ROM_BIN)" "$(ROM_HEX)"
	@echo "wrote $(ROM_HEX)"

current-rom:
	bash scripts/build-current-rom.sh

build: prepare
	$(MAKE) -C "$(TARGET_DIR)/srcsim" FRONTPANEL=NO INFOPANEL=NO build

run:
	@if [ ! -x "$(TARGET_BIN)" ]; then \
		echo 'error: targetsim is not built; run make build first' >&2; \
		exit 2; \
	fi
	@if [ ! -f "$(ROM_HEX)" ]; then \
		echo 'error: build/target-monitor.hex is missing; run make rom ROM_BIN=...' >&2; \
		exit 2; \
	fi
	TARGET_CF0="$(abspath $(CF0))" \
	TARGET_CF1="$(abspath $(CF1))" \
	TARGET_IDE_TRACE="$(IDE_TRACE)" \
	sh -c 'cd "$(TARGET_DIR)" && exec ./targetsim -z -c conf_3d/system.conf -r "$(abspath build)"'

smoke-cf:
	$(PYTHON) tools/make_smoke_cf.py "$(SMOKE_CF)"

smoke: build current-rom smoke-cf
	$(PYTHON) tools/run_boot_smoke.py \
		--targetsim "$(TARGET_BIN)" \
		--config "$(TARGET_DIR)/conf_3d/system.conf" \
		--romdir "$(abspath build)" \
		--cf0 "$(SMOKE_CF)"

test:
	$(PYTHON) -m unittest discover -s tests -v

clean:
	rm -rf build
