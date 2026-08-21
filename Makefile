PYTHON ?= python3
ROM_BIN ?=
ROM_HEX := build/target-monitor.hex
TARGET_DIR := build/z80pack-upstream/targets100sim
TARGET_BIN := $(TARGET_DIR)/targetsim
TARGET_PREPARED := $(TARGET_DIR)/.target-prepared
CF0_WORK := build/cf0-work.img
CF1_WORK := build/cf1-work.img
CF0 ?= $(CF0_WORK)
CF1 ?= $(CF1_WORK)
CF0_SOURCE ?=
CF1_SOURCE ?=
IDE_TRACE ?= 0
DSI0 ?=
DSI1 ?=
DSI_TRACE ?= 0
DSI_WRITE ?= 0
DSI_BOOTSTRAP ?= 0
SMOKE_CF := build/smoke-cf0.img

TARGET_INPUTS := \
	Makefile \
	scripts/bootstrap-z80pack.sh \
	scripts/prepare-targetsim.sh \
	emulator/conf/system.conf \
	emulator/conf/dsi-compat.conf \
	emulator/srcsim/simio.c \
	emulator/srcsim/target-ide.c \
	emulator/srcsim/target-ide.h \
	emulator/srcsim/target-dsi-fdc1.c \
	emulator/srcsim/target-dsi-fdc1.h

.PHONY: help bootstrap prepare rom current-rom build run dsi-compat cf-work cf-reset lab smoke-cf smoke test clean

help:
	@printf '%s\n' \
	  'make bootstrap                     Fetch pinned z80pack upstream' \
	  'make prepare                       Refresh target-machine overlay only when inputs changed' \
	  'make rom ROM_BIN=/path/monitor.bin Convert logical 4K ROM to Intel HEX' \
	  'make current-rom                   Build pinned target ROM only when needed' \
	  'make build                         Incrementally build targetsim' \
	  'make run                           Restart existing lab work images immediately' \
	  'make run IDE_TRACE=1               Restart with IDE command tracing enabled' \
	  'make run DSI0=/path/sd.img         Attach DSI FDC-1 SD drive A read-only' \
	  'make run DSI0=/path/sd.img DSI_BOOTSTRAP=1' \
	  '                                   Preload T0/S1 into 0000H-007FH while retaining target ROM/map' \
	  'make dsi-compat DSI0=/path/sd.img Run historical DSI image with 64K RAM/no target ROM' \
	  'make run DSI0=/path/a.img DSI1=/path/b.img DSI_TRACE=1' \
	  '                                   Attach/trace two DSI SD drives' \
	  'make cf-work CF0_SOURCE=/path/a.img [CF1_SOURCE=/path/b.img]' \
	  '                                   Create work copies only if they do not exist' \
	  'make cf-reset                      Delete disposable lab work copies' \
	  'make lab CF0_SOURCE=/path/a.img [CF1_SOURCE=/path/b.img]' \
	  '                                   First setup/build, then run the CP/M 3 lab' \
	  'make smoke                         Real-ROM IDE boot regression' \
	  'make test                          Run host-side regression tests' \
	  'make clean                         Remove all generated build output/work images' \
	  '' \
	  'Interactive targetsim sessions: press Ctrl-] for a clean emulator exit.'

bootstrap:
	bash scripts/bootstrap-z80pack.sh

$(TARGET_PREPARED): $(TARGET_INPUTS)
	bash scripts/prepare-targetsim.sh
	@touch "$@"

prepare: $(TARGET_PREPARED)

rom:
	@if [ -z "$(ROM_BIN)" ]; then \
		echo 'error: set ROM_BIN to IMSAI_TARGET_MONITOR_4K.bin' >&2; \
		exit 2; \
	fi
	$(PYTHON) tools/bin2ihex.py "$(ROM_BIN)" "$(ROM_HEX)"
	@echo "wrote $(ROM_HEX)"

$(ROM_HEX): scripts/build-current-rom.sh tools/bin2ihex.py
	bash scripts/build-current-rom.sh

current-rom: $(ROM_HEX)

$(TARGET_BIN): $(TARGET_PREPARED)
	$(MAKE) -C "$(TARGET_DIR)/srcsim" FRONTPANEL=NO INFOPANEL=NO build

build: $(TARGET_BIN)

run:
	@if [ ! -x "$(TARGET_BIN)" ]; then \
		echo 'error: targetsim is not built; run make lab or make build first' >&2; \
		exit 2; \
	fi
	@if [ ! -f "$(ROM_HEX)" ]; then \
		echo 'error: build/target-monitor.hex is missing; run make lab or make current-rom first' >&2; \
		exit 2; \
	fi
	@if [ ! -f "$(CF0)" ] && { [ -z "$(strip $(DSI0))" ] || [ ! -f "$(abspath $(DSI0))" ]; }; then \
		echo 'error: neither a CF0 image nor a DSI0 image is available' >&2; \
		echo '       run make lab CF0_SOURCE=/path/to/reference.img or set DSI0=/path/to/sd.img' >&2; \
		exit 2; \
	fi
	TARGET_IDE_TRACE="$(IDE_TRACE)" \
	TARGET_DSI_TRACE="$(DSI_TRACE)" \
	TARGET_DSI_WRITE="$(DSI_WRITE)" \
	TARGET_DSI_BOOTSTRAP="$(DSI_BOOTSTRAP)" \
	sh -c 'if [ -n "$(strip $(CF0))" ] && [ -f "$(abspath $(CF0))" ]; then export TARGET_CF0="$(abspath $(CF0))"; else unset TARGET_CF0; fi; if [ -n "$(strip $(CF1))" ] && [ -f "$(abspath $(CF1))" ]; then export TARGET_CF1="$(abspath $(CF1))"; else unset TARGET_CF1; fi; if [ -n "$(strip $(DSI0))" ] && [ -f "$(abspath $(DSI0))" ]; then export TARGET_DSI0="$(abspath $(DSI0))"; else unset TARGET_DSI0; fi; if [ -n "$(strip $(DSI1))" ] && [ -f "$(abspath $(DSI1))" ]; then export TARGET_DSI1="$(abspath $(DSI1))"; else unset TARGET_DSI1; fi; cd "$(TARGET_DIR)" && exec ./targetsim -z -c conf_3d/system.conf -r "$(abspath build)"'

dsi-compat: build
	@if [ -z "$(strip $(DSI0))" ] || [ ! -f "$(abspath $(DSI0))" ]; then \
		echo 'error: set DSI0 to a 256256-byte 77x26x128 single-density image' >&2; \
		exit 2; \
	fi
	TARGET_DSI0="$(abspath $(DSI0))" \
	TARGET_DSI_TRACE="$(DSI_TRACE)" \
	TARGET_DSI_WRITE="$(DSI_WRITE)" \
	TARGET_DSI_BOOTSTRAP=1 \
	sh -c 'if [ -n "$(strip $(DSI1))" ] && [ -f "$(abspath $(DSI1))" ]; then export TARGET_DSI1="$(abspath $(DSI1))"; else unset TARGET_DSI1; fi; unset TARGET_CF0 TARGET_CF1; cd "$(TARGET_DIR)" && exec ./targetsim -z -c conf_3d/dsi-compat.conf'

cf-work:
	@if [ -z "$(CF0_SOURCE)" ]; then \
		echo 'error: set CF0_SOURCE to the archived/reference CF image' >&2; \
		exit 2; \
	fi
	@if [ -f "$(CF0_WORK)" ]; then \
		echo 'preserving existing $(CF0_WORK)'; \
		echo '  use make cf-reset before changing CF0_SOURCE'; \
	else \
		$(PYTHON) tools/make_cf_workcopy.py "$(CF0_SOURCE)" "$(CF0_WORK)"; \
	fi
	@if [ -n "$(CF1_SOURCE)" ]; then \
		if [ -f "$(CF1_WORK)" ]; then \
			echo 'preserving existing $(CF1_WORK)'; \
			echo '  use make cf-reset before changing CF1_SOURCE'; \
		else \
			$(PYTHON) tools/make_cf_workcopy.py "$(CF1_SOURCE)" "$(CF1_WORK)"; \
		fi; \
	fi

cf-reset:
	rm -f "$(CF0_WORK)" "$(CF1_WORK)"
	@echo 'disposable CF work copies removed; reference images were not touched'

lab: build current-rom cf-work
	$(MAKE) run CF0="$(CF0_WORK)" CF1="$(if $(strip $(CF1_SOURCE)),$(CF1_WORK),)" IDE_TRACE="$(IDE_TRACE)" DSI0="$(DSI0)" DSI1="$(DSI1)" DSI_TRACE="$(DSI_TRACE)" DSI_WRITE="$(DSI_WRITE)" DSI_BOOTSTRAP="$(DSI_BOOTSTRAP)"

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
