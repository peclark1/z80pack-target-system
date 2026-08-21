# Emulator Layer

This directory contains the target-specific overlay applied to the pinned z80pack `imsaisim` source by `scripts/prepare-targetsim.sh`.

## Current implementation

Implemented now:

- Z80 selected as the target CPU model
- 4 MHz nominal CPU setting
- RAM `0000H-EFFFH`
- ROM `F000H-FFFFH`
- reset / power-on jump to `F000H`
- Console I/O V2 at `00H/01H`
  - host terminal backend
  - target RX-ready bit `02H`
  - target TX-ready bit `04H`
- Dual IDE/CF V3 at `30H-34H`
  - 8255-visible A/B/C/control/drive-select interface
  - two flat 512-byte-sector image files
  - LBA READ SECTORS (`20H`)
  - LBA WRITE SECTORS (`30H`)
  - IDENTIFY DEVICE (`ECH`)
  - FLUSH CACHE (`E7H`) and SET FEATURES (`EFH`) accepted for compatibility
  - target monitor's exact PPI `RD`, `WR`, and `RESET` strobe sequence
  - optional host-side ATA command tracing
- IMSAI front-panel programmed input at `FFH`
  - headless value controlled by `fp_port` in `system.conf`
- MIO serial subset at `42H/43H`
  - uses z80pack's second IMSAI SIO channel as the host-side backend
  - TX-ready bit `01H`, RX-ready bit `02H`
  - local UNIX socket backend `targets100sim.mio`

Not implemented yet:

- Serial I/O V3 / Z85C30 channel A at `A1H/A3H`
- Altair FDC/FDC+ integration
- CP/M disk-image build/install automation
- broad ATA command coverage beyond the commands required by current firmware/BIOS work
- detailed instruction-level I/O tracing beyond the optional IDE command trace

## Dual IDE/CF abstraction

The real board exposes the ATA task-file through an 8255 PPI. The emulator preserves that interface instead of letting the ROM access a host image directly. This means the real monitor and BIOS still have to perform the same sequence of writes to ports `30H-34H`, assert the same PPI control bits, poll the same ATA status bits, and transfer the same 16-bit data words.

The backing images are selected through environment variables supplied by `make run`:

```text
TARGET_CF0   first CF image
TARGET_CF1   second CF image
```

Missing images behave as not-ready devices. Writable files permit ATA WRITE commands; read-only files remain readable and reject writes.

## Why reuse z80pack SIO backends?

The physical Console I/O and MIO are modeled at their Z80-visible register interface, while z80pack's mature terminal/socket code provides host-side character transport. The target-specific wrapper translates status bits where required.

This avoids emulating irrelevant VGA, PS/2, UART, and TTL internals while still running the exact target firmware I/O instructions unchanged.

## Generated machine

`make prepare` creates:

```text
build/z80pack-upstream/targets100sim/
```

by copying the pinned upstream `imsaisim` machine and applying this repository's target-specific source/configuration overlay. Generated upstream source is intentionally not committed.
