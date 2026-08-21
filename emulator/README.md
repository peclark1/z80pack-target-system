# Emulator Layer

This directory contains the target-specific overlay applied to the pinned z80pack `imsaisim` source by `scripts/prepare-targetsim.sh`.

## Current M1 implementation

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
- IMSAI front-panel programmed input at `FFH`
  - headless value controlled by `fp_port` in `system.conf`
- MIO serial subset at `42H/43H`
  - uses z80pack's second IMSAI SIO channel as the host-side backend
  - TX-ready bit `01H`, RX-ready bit `02H`
  - local UNIX socket backend `targets100sim.mio`

Not implemented yet:

- Dual IDE/CF V3 at `30H-34H`
- Serial I/O V3 / Z85C30 channel A at `A1H/A3H`
- Altair FDC/FDC+ integration
- CP/M disk-image build/install automation
- detailed I/O/sector tracing

The monitor will therefore be able to execute its early reset/console path once a valid target ROM is supplied, but its current startup calls `IDE_INIT`; meaningful boot testing requires the Dual IDE/CF model next.

## Why reuse z80pack SIO backends?

The physical Console I/O and MIO are modeled at their Z80-visible register interface, while z80pack's mature terminal/socket code provides host-side character transport. The target-specific wrapper translates status bits where required.

This avoids emulating irrelevant VGA, PS/2, UART, and TTL internals while still running the exact target firmware I/O instructions unchanged.

## Generated machine

`make prepare` creates:

```text
build/z80pack-upstream/targets100sim/
```

by copying the pinned upstream `imsaisim` machine and applying this repository's target-specific source/configuration overlay. Generated upstream source is intentionally not committed.
