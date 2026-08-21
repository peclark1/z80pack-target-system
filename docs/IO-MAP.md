# Target I/O Map

This is the authoritative emulator-side port map for the current IMSAI target. Values are taken from the current 4K target monitor project and should remain synchronized with it.

| Port | Direction | Device | Meaning / emulator handler |
|---:|---|---|---|
| `00H` | IN | Console I/O V2 | Status. RX ready=`02H`, TX ready=`04H`. |
| `01H` | IN/OUT | Console I/O V2 | Keyboard input / display output. |
| `08H-0AH` | IN/OUT | Altair FDC/FDC+ | Altair-compatible floppy-controller interface; exact handler assignment will follow z80pack's 88-DCDD model. |
| `30H` | IN/OUT | Dual IDE/CF V3 | 8255 Port A (`IDE_A`). |
| `31H` | IN/OUT | Dual IDE/CF V3 | 8255 Port B (`IDE_B`). |
| `32H` | IN/OUT | Dual IDE/CF V3 | 8255 Port C (`IDE_C`), ATA register select/control bits. |
| `33H` | OUT | Dual IDE/CF V3 | 8255 control (`IDE_CTRL`). Current monitor uses `92H` for read configuration and `80H` for write configuration. |
| `34H` | OUT | Dual IDE/CF V3 | Drive select (`IDE_DRIVE`). |
| `42H` | IN/OUT | IMSAI MIO SIO | Serial data. |
| `43H` | IN/OUT | IMSAI MIO SIO | Status/control. TX ready bit 0, RX ready bit 1 in current hardware configuration. |
| `A1H` | IN/OUT | Serial I/O V3 A | Z85C30 channel-A control/status. RR0 RX ready bit 0, TX ready bit 2. |
| `A3H` | IN/OUT | Serial I/O V3 A | Z85C30 channel-A data. |
| `FFH` | IN | IMSAI front panel | Programmed-input / sense-switch byte. Low two bits select monitor console. |

## Dual IDE/CF software contract

The current monitor defines:

```text
IDE_A           30H
IDE_B           31H
IDE_C           32H
IDE_CTRL        33H
IDE_DRIVE       34H

IDE_RD_CFG      92H
IDE_WR_CFG      80H
IDE_RESET_BIT   80H
IDE_RD_BIT      40H
IDE_WR_BIT      20H

ATA register selectors used by the monitor:
DATA            08H
COUNT           0AH
SECTOR          0BH
CYL_LO          0CH
CYL_HI          0DH
SDH             0EH
STATUS/COMMAND  0FH
READ command    20H
```

The emulator should initially implement exactly the transaction sequence used by the monitor instead of attempting a complete ATA implementation. Additional commands can be added from observed CP/M BIOS requirements.

## Console selection contract

An `IN FFH` at reset returns the target's front-panel byte. The monitor masks bits 1:0:

```text
00 -> Console I/O V2
01 -> Serial I/O V3 channel A
10 -> IMSAI MIO SIO
11 -> reserved / Console I/O fallback
```

All three console implementations should ultimately expose the same effective monitor primitives:

- `CONST`: character available?
- `CONIN`: read character
- `CONOUT`: write character

## Unassigned ports

Unless a modeled board requires otherwise, unassigned input ports should use the same default behavior as the selected z80pack machine base. We will document any intentional differences once the target-specific `simio.c` is implemented.

## Change control

When the physical target's port configuration changes, update the 4K monitor project first (or in the same change set), then update this table and emulator handlers. Do not introduce emulator-only alternate port assignments.
