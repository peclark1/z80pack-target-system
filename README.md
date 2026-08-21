# z80pack Target System

A z80pack-based emulator for the software-visible hardware profile of the IMSAI 8080 target system.

The goal is not to create a generic CP/M machine. The goal is to run the **same monitor ROM, CP/M boot code, BIOS, disk images, I/O addresses, and console-selection logic** used by the physical IMSAI so that firmware and CP/M system-generation work can be developed and tested before moving to the real hardware.

## Physical target represented

- IMSAI 8080 chassis/front panel
- North Star ZPB-A2 Z80A CPU
  - reset / power-on jump target: `F000H`
- Modified Altair FDC+
  - RAM: `0000H-EFFFH`
  - ROM: `F000H-FFFFH`
- S100Computers Console I/O V2 at `00H-01H`
- S100Computers Dual IDE/CF V3 at `30H-34H`
- IMSAI MIO SIO at `42H-43H`
- S100Computers Serial I/O V3 channel A at `A1H/A3H`
- IMSAI programmed-input / sense switches at `FFH`
- Altair-compatible FDC interface for floppy boot support

The emulator must conform to the real hardware interface. We do not plan to change ROM or BIOS code merely to make emulation easier.

## Why this project exists

The first major use case is a CP/M 3 development laboratory. A typical loop should eventually be:

1. edit BIOS/configuration sources on Linux;
2. assemble/link using either host tools or the original CP/M utilities;
3. run `GENCPM`;
4. install the resulting `CPM3.SYS` into a disposable CF image;
5. boot the image through the real target monitor ROM in z80pack;
6. test console I/O, both IDE drives, warm boot, directory access, hashing, and TPA;
7. repeat quickly while optimizing common-memory usage and TPA.

This should make experiments such as changing `MEMTOP`, buffer placement, allocation vectors, directory hashing, BIOS placement, and driver size much safer and faster than repeated tests on physical media.

## Repository layout

```text
.
├── docs/                 Hardware, I/O, development and CP/M lab notes
├── emulator/             Target-machine z80pack configuration and overlays
├── rom/                  ROM integration notes; generated ROMs stay untracked
├── cpm3/                 CP/M 3 source/config/build workspace
├── disks/                Disk-image integration notes; images stay untracked
├── scripts/              Bootstrap/build helpers
├── tools/                Small host-side utilities
├── tests/                Host-side regression tests
└── Makefile
```

## Development strategy

We intentionally do **not** vendor a complete copy of z80pack into this repository. `scripts/bootstrap-z80pack.sh` checks out a pinned upstream z80pack revision into `build/z80pack-upstream`. Our target-specific machine files and device implementations live here and will be applied as an overlay.

This keeps Udo Munk's upstream source clearly separated from our hardware model and makes future upstream updates explicit and reviewable.

The initial upstream baseline is commit:

```text
91fd28eb04e675c2127df88ed3f40675e15282e2
```

## Milestones

### M1 - ROM console

- Z80 execution
- RAM `0000H-EFFFH`
- ROM `F000H-FFFFH`
- reset/POJ to `F000H`
- IMSAI front-panel switch byte at `FFH`
- Console I/O V2 at `00H/01H`
- boot the actual 4K target monitor ROM and interact with its prompt

### M2 - Dual IDE/CF

- emulate the board's `30H-34H` software interface
- two CF image files
- implement the ATA subset used by the monitor and CP/M BIOS
- boot an existing CP/M 3 CF image through the real monitor

### M3 - CP/M 3 lab

- repeatable BIOS / `GENCPM` build workflow
- disposable test-image generation
- scripted boot tests
- TPA reporting and configuration comparison

### M4 - Additional target I/O

- MIO SIO subset at `42H/43H`
- Serial I/O V3 channel A at `A1H/A3H`
- front-panel console-selection regression tests
- Altair FDC/FDC+ compatible floppy path

Later additions can include the DSI disk subsystem, VTI, interrupt fidelity, and more detailed timing when software requires them.

## Getting started

Clone this repository and fetch the pinned z80pack source:

```sh
git clone https://github.com/peclark1/z80pack-target-system.git
cd z80pack-target-system
make bootstrap
```

To convert the logical 4K monitor `.bin` produced by `s100-target-system-4k-master-rom` into Intel HEX at `F000H` for z80pack:

```sh
make rom ROM_BIN=/path/to/IMSAI_TARGET_MONITOR_4K.bin
```

The generated file is `build/target-monitor.hex`.

Run host-side tests with:

```sh
make test
```

## Related project

The firmware source of truth is:

- `peclark1/s100-target-system-4k-master-rom`

Its hardware map and monitor behavior are authoritative for the emulator whenever the two projects overlap.
