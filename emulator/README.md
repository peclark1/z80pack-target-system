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
- Serial I/O V3 DLP-USB245R host-link subset
  - USB FIFO handshake/status at `AAH`
  - USB FIFO data at `ACH`
  - RX-ready bit 7 and TX-ready bit 6 are active low, matching the physical board
  - exposed to Linux as a pseudo-terminal suitable for pySerial
  - stable default endpoint `/tmp/targets100sim-usb-<uid>`
  - optional endpoint override with `TARGET_SERIALIO_USB_TTY`

Not implemented yet:

- Serial I/O V3 Z85C30 channel A at `A1H/A3H`
- full Serial I/O V3 8255 parallel-port behavior at `A8H-ABH`
- CP/M disk-image build/install automation
- broad ATA command coverage beyond the commands required by current firmware/BIOS work
- detailed instruction-level I/O tracing beyond the optional IDE command trace

## Serial I/O USB host-link bridge

The physical Serial I/O V3 board presents the DLP-USB245R FIFO to the Z80 as a byte data register plus active-low FIFO-ready signals. `HOST.COM` only needs that software-visible subset, so the emulator does not need to model USB packets or a UART baud clock.

At emulator startup a PTY master is allocated and a stable symlink is created for the slave side:

```text
/tmp/targets100sim-usb-<uid> -> /dev/pts/N
```

The emulator prints the actual mapping when it starts. The production `s100-host-link` utility can open the stable path through pySerial exactly as it opens a physical USB serial device. Closing and reopening Host Link does not require restarting the emulator; `HOST.COM` continues its normal readiness advertisements.

The endpoint may be changed before starting the emulator:

```sh
TARGET_SERIALIO_USB_TTY=/tmp/my-imsai-usb make run
```

A stale symlink created by the same user is replaced on the next start. A non-symlink or another user's path is never overwritten.

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

The Serial I/O USB FIFO is kept separate because its physical software interface uses active-low DLP-USB245R handshakes rather than the IMSAI SIO ready-bit convention. A PTY still gives the Linux side the same familiar serial-device API.

This avoids emulating irrelevant VGA, PS/2, UART, and USB internals while still running the exact target firmware and CP/M I/O instructions unchanged.

## Generated machine

`make prepare` creates:

```text
build/z80pack-upstream/targets100sim/
```

by copying the pinned upstream `imsaisim` machine and applying this repository's target-specific source/configuration overlay. Generated upstream source is intentionally not committed.
