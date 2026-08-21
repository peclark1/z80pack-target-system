# z80pack Target System

A z80pack-based emulator for the software-visible hardware profile of the IMSAI 8080 target system.

The goal is not to create a generic CP/M machine. The goal is to run the **same monitor ROM, CP/M boot code, BIOS, disk images, I/O addresses, and console-selection logic** used by the physical IMSAI so that firmware and CP/M system-generation work can be developed and tested before moving to the real hardware.

## Current verified status

The emulator now passes an end-to-end CI smoke test using the **actual current 4K target monitor source**:

1. build the target monitor with PASMO;
2. verify the logical 4K image;
3. load it read-only at `F000H-FFFFH`;
4. start the Z80 at `F000H`;
5. read the IMSAI sense-switch byte from `FFH`;
6. use Console I/O at `00H/01H`;
7. initialize the emulated Dual IDE/CF through ports `30H-34H`;
8. issue ATA READ SECTORS (`20H`) for LBA 1, count 12;
9. transfer the loader through the emulated 8255/ATA data path to `0100H`;
10. validate the loader's `31H` signature and execute it successfully.

The generated machine reports exactly the current target's CPU-visible memory profile: 60K RAM at `0000H-EFFFH`, 4K ROM at `F000H-FFFFH`, POJ/reset at `F000H`, and no additional MMU RAM banks exposed.

This proves the monitor/console/front-panel/IDE boot path. The next major validation is to attach a copy of the real CP/M 3 CF image and boot the real CPMLDR/CPM3.SYS rather than the small synthetic smoke-test loader.

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

### M1 - ROM console — working

- Z80 execution
- RAM `0000H-EFFFH`
- ROM `F000H-FFFFH`
- reset/POJ to `F000H`
- IMSAI front-panel switch byte at `FFH`
- Console I/O V2 at `00H/01H`
- boot and interact with the actual 4K target monitor ROM

### M2 - Dual IDE/CF — monitor boot path working

- board's `30H-34H` software interface implemented
- two CF image files supported
- ATA READ, WRITE, IDENTIFY and required compatibility commands implemented
- real monitor IDE boot path verified through a synthetic CPMLDR image
- remaining acceptance step: boot an existing real CP/M 3 CF image

### M3 - CP/M 3 lab

- repeatable BIOS / `GENCPM` build workflow
- disposable test-image generation
- scripted boot tests
- TPA reporting and configuration comparison

### M4 - Additional target I/O

- MIO SIO subset at `42H/43H` — initial serial mapping implemented
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

Build the emulator:

```sh
make build
```

To convert the logical 4K monitor `.bin` produced by `s100-target-system-4k-master-rom` into Intel HEX at `F000H` for z80pack:

```sh
make rom ROM_BIN=/path/to/IMSAI_TARGET_MONITOR_4K.bin
```

Or build the pinned current monitor source automatically and run the complete IDE boot smoke test:

```sh
make smoke
```

For local use with real CF image copies, place them at `disks/cf0.img` and `disks/cf1.img` or supply alternate paths:

```sh
make run CF0=/path/to/cf0.img CF1=/path/to/cf1.img
```

ATA command tracing can be enabled with:

```sh
make run IDE_TRACE=1
```

Run host-side tests with:

```sh
make test
```

## Related project

The firmware source of truth is:

- `peclark1/s100-target-system-4k-master-rom`

Its hardware map and monitor behavior are authoritative for the emulator whenever the two projects overlap.
