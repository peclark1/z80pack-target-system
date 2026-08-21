# z80pack Target System

A z80pack-based emulator for the software-visible hardware profile of the IMSAI 8080 target system.

The goal is not to create a generic CP/M machine. The goal is to run the **same monitor ROM, CP/M boot code, BIOS, disk images, I/O addresses, and console-selection logic** used by the physical IMSAI so that firmware and CP/M system-generation work can be developed and tested before moving to the real hardware.

## Current verified status

The emulator now boots the **actual target CP/M 3 images** through the actual current 4K monitor ROM and emulated Dual IDE/CF V3 interface.

The automated CI smoke test still verifies the complete low-level boot path:

1. build the target monitor with PASMO;
2. verify the logical 4K image;
3. load it read-only at `F000H-FFFFH`;
4. start the Z80 at `F000H`;
5. read the IMSAI sense-switch byte from `FFH`;
6. use Console I/O at `00H/01H`;
7. initialize the emulated Dual IDE/CF through ports `30H-34H`;
8. issue ATA READ SECTORS (`20H`) for LBA 1, count 12;
9. transfer CPMLDR through the emulated 8255/ATA data path to `0100H`;
10. validate and execute the loader.

The generated machine reports exactly the current target's CPU-visible memory profile: 60K RAM at `0000H-EFFFH`, 4K ROM at `F000H-FFFFH`, POJ/reset at `F000H`, and no additional MMU RAM banks exposed.

Real-image validation currently includes:

- `S100-cpm3-nonbanked-prop-dualcf-dsi-v3.0.img`
  - reaches `A>`;
  - BIOS3 at `B800H`, BDOS3 at `9700H`;
  - **37K TPA**.
- `S100-cpm3-nonbanked-prop-dualcf-dsi-v3.1-hashoff-test.img`
  - reaches `A>`;
  - BIOS3 at `DA00H`, BDOS3 at `BB00H`;
  - **46K TPA**.
- A:/B: Dual IDE/CF selection and directory reads work using two attached image files.
- CP/M file creation and read-back through the real BIOS/ATA WRITE path work on disposable full-geometry work copies.

The v3.1 image therefore recovers **9K of TPA** versus the v3.0 control while remaining bootable and usable in the emulator.

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

The first major use case is a CP/M 3 development laboratory. The working loop is now:

1. edit BIOS/configuration sources on Linux;
2. assemble/link using either host tools or the original CP/M utilities;
3. run `GENCPM`;
4. install the resulting `CPM3.SYS` into a disposable CF work image;
5. boot the image through the real target monitor ROM in z80pack;
6. test console I/O, both IDE drives, warm boot, directory access, hashing, file writes, and TPA;
7. repeat quickly while optimizing common-memory usage and TPA.

This makes experiments such as changing `MEMTOP`, buffer placement, allocation vectors, directory hashing, BIOS placement, and driver size much safer and faster than repeated tests on physical media.

## Repository layout

```text
.
├── docs/                 Hardware, I/O, development and CP/M lab notes
├── emulator/             Target-machine z80pack configuration and overlays
├── rom/                  ROM integration notes; generated ROMs stay untracked
├── cpm3/                 CP/M 3 source/config/build workspace
├── disks/                Disk-image integration notes; images stay untracked
├── scripts/              Bootstrap/build helpers
├── tools/                Host-side utilities, including CF work-copy creation
├── tests/                Host-side regression tests
└── Makefile
```

## Development strategy

We intentionally do **not** vendor a complete copy of z80pack into this repository. `scripts/bootstrap-z80pack.sh` checks out a pinned upstream z80pack revision into `build/z80pack-upstream`. Our target-specific machine files and device implementations live here and are applied as an overlay.

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

### M2 - Dual IDE/CF — working

- board's `30H-34H` software interface implemented
- two CF image files supported
- ATA READ, WRITE, IDENTIFY and required compatibility commands implemented
- real monitor IDE boot path verified
- real CPMLDR and `CPM3.SYS` boot verified
- A:/B: drive switching and directory access verified
- file creation/read-back through the BIOS write path verified

### M3 - CP/M 3 lab — operational baseline

- disposable full-geometry CF work-copy generation
- real-image boot and TPA comparison
- IDE read/write tracing
- host-side and full-ROM CI regression tests
- next: automate BIOS/`GENCPM` candidate generation and configuration matrix testing

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

### Run the CP/M 3 lab safely

Archived/reference CF images may be compact files that stop after the last meaningful sector, while the BIOS exposes an 8 MiB logical disk. For writable sessions, do not modify the archive in place. Create a disposable full-geometry work image:

```sh
make cf-work CF0_SOURCE=/path/to/reference.img
```

For two emulated CF devices:

```sh
make cf-work \
  CF0_SOURCE=/path/to/drive-a.img \
  CF1_SOURCE=/path/to/drive-b.img
```

The work copies are created as `build/cf0-work.img` and `build/cf1-work.img` and expanded to the BIOS's 8 MiB logical capacity.

Build everything and enter the lab in one command:

```sh
make lab CF0_SOURCE=/path/to/reference.img IDE_TRACE=1
```

or with both drives:

```sh
make lab \
  CF0_SOURCE=/path/to/drive-a.img \
  CF1_SOURCE=/path/to/drive-b.img \
  IDE_TRACE=1
```

You can still run arbitrary image copies directly:

```sh
make run CF0=/path/to/cf0.img CF1=/path/to/cf1.img
```

ATA command tracing can be enabled with `IDE_TRACE=1`.

Run host-side tests with:

```sh
make test
```

See `docs/CPM3-LAB.md` for the verified real-image results and planned GENCPM/TPA test matrix.

## Related project

The firmware source of truth is:

- `peclark1/s100-target-system-4k-master-rom`

Its hardware map and monitor behavior are authoritative for the emulator whenever the two projects overlap.
