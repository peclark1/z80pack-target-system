PYTHON ?= python3
ROM_BIN ?=
ROM_HEX := build/target-monitor.hex

.PHONY: help bootstrap rom test clean

help:
	@printf '%s\n' \
	  'make bootstrap                     Fetch pinned z80pack upstream' \
	  'make rom ROM_BIN=/path/monitor.bin Convert logical 4K ROM to Intel HEX' \
	  'make test                          Run host-side regression tests' \
	  'make clean                         Remove generated build output'

bootstrap:
	bash scripts/bootstrap-z80pack.sh

rom:
	@if [ -z "$(ROM_BIN)" ]; then \
		echo 'error: set ROM_BIN to IMSAI_TARGET_MONITOR_4K.bin' >&2; \
		exit 2; \
	fi
	$(PYTHON) tools/bin2ihex.py "$(ROM_BIN)" "$(ROM_HEX)"
	@echo "wrote $(ROM_HEX)"

test:
	$(PYTHON) -m unittest discover -s tests -v

clean:
	rm -rf build
