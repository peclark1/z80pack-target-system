PYTHON ?= python3
ROM_BIN ?=
ROM_HEX := build/target-monitor.hex
TARGET_DIR := build/z80pack-upstream/targets100sim
TARGET_BIN := $(TARGET_DIR)/targetsim

.PHONY: help bootstrap prepare rom build run test clean

help:
	@printf '%s\n' \
	  'make bootstrap                     Fetch pinned z80pack upstream' \
	  'make prepare                       Create target-machine source overlay' \
	  'make rom ROM_BIN=/path/monitor.bin Convert logical 4K ROM to Intel HEX' \
	  'make build                         Build the first targetsim emulator' \
	  'make run                           Run targetsim with build/target-monitor.hex' \
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
	cd "$(TARGET_DIR)" && ./targetsim -z -c conf_3d/system.conf -r "$(abspath build)"

test:
	$(PYTHON) -m unittest discover -s tests -v

clean:
	rm -rf build
