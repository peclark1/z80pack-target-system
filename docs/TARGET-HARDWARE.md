# Target Hardware Profile

This document defines the physical IMSAI target that the emulator is intended to reproduce at the software-visible level.

## Design rule

The emulator conforms to the hardware. Firmware and CP/M BIOS code should not need emulator-specific alternate port numbers, memory maps, status bits, or boot paths.

Where full electrical fidelity is unnecessary, emulate the behavior visible to Z80 software rather than the internal TTL implementation of a board.

## CPU and reset behavior

- CPU: Z80-compatible execution matching the North Star ZPB-A2 Z80A CPU for normal software-visible behavior.
- Reset / power-on jump entry: `F000H`.
- Interrupt and front-panel timing fidelity can be added later when required by software.

## Memory map

| Address range | Size | Physical target | Emulator behavior |
|---|---:|---|---|
| `0000H-EFFFH` | 60 KiB | Modified Altair FDC+ RAM | Read/write RAM |
| `F000H-FFFFH` | 4 KiB | Altair FDC+ ROM window | Read-only target monitor ROM |

The logical 4K ROM image is the same `F000H-FFFFH` image produced by the `s100-target-system-4k-master-rom` project. The physical 8K EEPROM programmer image used by the FDC+ is not the preferred emulator input because its lower 4K is device-placement padding rather than part of the logical CPU map.

## Current target devices

### Console I/O V2

- Ports: `00H-01H`
- `00H`: status
- `01H`: data
- Monitor expectations:
  - RX ready: status bit 1 (`02H`)
  - TX ready: status bit 2 (`04H`)

For the first emulator milestone, this can map directly to a host terminal/PTY. VGA and PS/2 electrical details are outside the required abstraction.

### Dual IDE/CF V3

- Ports: `30H-34H`
- Two CF devices are required.
- The monitor currently uses the board's 8255-style interface and ATA READ command path.
- The emulator should expand ATA support only as the monitor, CP/M BIOS, or diagnostics require it.

Initial backing storage should be ordinary image files so the same images can be copied to physical CF media after validation.

### IMSAI MIO SIO subset

Only the serial portion is currently in scope.

- Board range: `40H-43H`
- SIO data: `42H`
- SIO status/control: `43H`
- Verified physical configuration: 19,200 baud, 8N1
- Monitor status mapping:
  - TX ready: bit 0 (`01H`)
  - RX ready: bit 1 (`02H`)

The parallel ports and other MIO functions are deliberately deferred.

### Serial I/O V3 channel A

- Control: `A1H`
- Data: `A3H`
- Z85C30/SCC-style interface
- Monitor expectations from RR0:
  - RX ready: bit 0 (`01H`)
  - TX ready: bit 2 (`04H`)

A first implementation only needs the asynchronous register behavior exercised by the monitor and CP/M software. Full SCC feature/timing fidelity is not required initially.

### IMSAI front-panel programmed input

- Port: `FFH`
- This is the real IMSAI programmed-input/sense-switch port.
- `EFH` is not used by this target.

The current monitor interprets the low two bits as the console selector:

| SW09 | SW08 | Low bits | Console |
|---:|---:|---:|---|
| 0 | 0 | `00` | Console I/O V2 |
| 0 | 1 | `01` | Serial I/O V3 channel A |
| 1 | 0 | `10` | IMSAI MIO SIO |
| 1 | 1 | `11` | Reserved; monitor falls back to Console I/O |

The emulator should allow the `FFH` input byte to be set easily from configuration or a runtime control.

### Altair FDC+

The physical FDC+ is software-compatible with the original Altair disk-controller interface for normal floppy operation. z80pack already contains an Altair 88-DCDD device model, so the preferred path is to reuse/adapt that model rather than write a new floppy controller from scratch.

FDC+-specific features should be modeled only when software uses them.

## Future hardware

Not part of the initial emulator acceptance criteria:

- Digital Systems disk subsystem
- Polymorphic VTI
- MIO parallel ports
- Serial I/O channel B
- RTC/time/date hardware
- speech interface
- extended/banked RAM beyond the current 64K CPU-visible target

These can be added incrementally without changing the base target contract.

## Acceptance principle

A binary that works in the emulator should be intended to run unchanged on the IMSAI. Differences that are unavoidable because the emulator abstracts physical hardware must be documented explicitly.
