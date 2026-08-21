# CP/M 3 Development Lab

One of the primary goals of this emulator is to make CP/M 3 system generation, BIOS development, and TPA optimization fast and repeatable.

## Verified real-image milestone — 2026-08-21

The emulator now boots the actual non-banked target CP/M 3 images through the actual 4K target monitor ROM and the emulated Dual IDE/CF V3 interface.

Verified with `S100-cpm3-nonbanked-prop-dualcf-dsi-v3.0.img`:

```text
CP/M V3.0 Loader
 BIOS3    SPR  B800  0B00
 BDOS3    SPR  9700  2100
 37K TPA

CP/M 3 NON-BANKED - ZSOS/DSI CLEAN V2.0
A:IDE0 B:IDE1 C:DSI8-0 D:DSI8-1
A>
```

Verified with `S100-cpm3-nonbanked-prop-dualcf-dsi-v3.1-hashoff-test.img`:

```text
CP/M V3.0 Loader
 BIOS3    SPR  DA00  0B00
 BDOS3    SPR  BB00  1F00
 46K TPA

CP/M 3 NON-BANKED - ZSOS/DSI CLEAN V2.0
A:IDE0 B:IDE1 C:DSI8-0 D:DSI8-1
A>
```

The v3.1 image therefore recovers 9K of TPA versus the v3.0 gold/control image while still reaching the CCP prompt.

With two image files attached, drive switching and directory access were also verified:

- `A:` uses emulated CF0;
- `B:` selects emulated CF1;
- `DIR` works on both drives;
- switching back to `A:` restores CF0 access.

A real write/read test was performed on a disposable full-geometry v3.1 work copy using PIP. CP/M created `ZZTEMP.TXT` through ATA WRITE commands and then read it back with `TYPE`, producing:

```text
HELLO FROM TARGETSIM
```

No CPU trap occurred during the full-geometry write test.

## Compact reference images vs writable work copies

The IDE/CF BIOS defines this logical geometry:

```text
physical sector size:   512 bytes
sectors per track:      64
tracks:                 256
logical capacity:       8,388,608 bytes (8 MiB)
```

Some archived/reference images are intentionally truncated after their last meaningful sector. That is safe for boot and read-only regression testing, but normal CP/M allocation can legitimately write beyond the compact file's EOF.

For example, the current compact v3.1 image is 3,074,048 bytes (6004 sectors). A PIP file-creation test legitimately reached LBA 6004, which exists on a real CF card but is one sector beyond the compact file.

Never expand or modify the archived image in place. Create a disposable work copy instead:

```sh
make cf-work CF0_SOURCE=/path/to/reference.img
```

For two IDE drives:

```sh
make cf-work \
  CF0_SOURCE=/path/to/drive-a.img \
  CF1_SOURCE=/path/to/drive-b.img
```

This creates:

```text
build/cf0-work.img
build/cf1-work.img
```

and expands each work copy to the full 8 MiB logical geometry while leaving the source image untouched.

To build the current ROM, build targetsim, make the work copy/copies, and enter the CP/M lab in one command:

```sh
make lab CF0_SOURCE=/path/to/reference.img IDE_TRACE=1
```

or with both CF devices:

```sh
make lab \
  CF0_SOURCE=/path/to/drive-a.img \
  CF1_SOURCE=/path/to/drive-b.img \
  IDE_TRACE=1
```

## Desired development loop

```text
edit BIOS/configuration
        |
assemble/link
        |
run GENCPM
        |
install CPM3.SYS into disposable CF image
        |
boot through actual target monitor ROM
        |
exercise console, disks, warm boot and TPA
        |
compare result / repeat
```

The emulator should make it cheap to try configurations that might hang or corrupt a test image on the physical system.

## Why TPA testing belongs here

TPA depends on the complete generated memory layout, not just one GENCPM answer. Changes in BIOS size, common memory, directory buffers, allocation vectors, hashing, resident modules, and MEMTOP can interact.

A virtual target gives us full visibility into that layout and lets us test several candidate builds without reprogramming ROMs or repeatedly writing physical CF media.

## Initial test matrix

Standardize builds around candidate top-of-memory values such as:

```text
EB
EC
ED
EE
EF
F0
```

The exact valid range is determined by the generated system and the fixed `F000H-FFFFH` ROM window. `F0` is a boundary check, not an assumption that CP/M may occupy ROM space.

For every candidate build record:

- GENCPM parameters used
- BIOS3 load/base address
- BDOS/common placement
- reported TPA
- whether cold boot reaches `A>`
- whether warm boot succeeds
- `DIR A:` result
- `DIR B:` result
- representative file read
- representative file write on a disposable image
- hashing enabled/disabled
- directory buffer strategy
- any emulator trace or memory-map anomaly

## Minimum boot regression

A candidate should not be considered stable merely because it prints a CP/M banner. The basic regression should include:

1. cold boot through the target 4K ROM IDE boot path;
2. reach the CP/M prompt;
3. report/record TPA;
4. `DIR A:`;
5. `DIR B:` when the second CF is configured;
6. execute a small transient command;
7. warm boot back to the CCP;
8. repeat directory access after warm boot;
9. create and read back a small file on a disposable full-geometry work image.

## Build artifacts

Generated system files and test disk images should normally stay out of Git unless there is a specific reason to preserve a known reference image. The repository should keep:

- source/configuration inputs;
- scripts that generate the result;
- compact manifests/checksums for known-good results;
- captured console logs when useful for regression comparison.

## Historical CP/M tools

Where practical, use the original CP/M tools inside the emulator for target-system generation, including tools such as `RMAC`, `LINK`, `GENCPM`, `GENCOM`, `SID`, and `DDT`. Host-side tools can still be used where they improve reproducibility.

The long-term goal is not to force every build step onto Linux or CP/M. It is to make the process reproducible and easy to inspect.

## Debug visibility to add

Useful emulator diagnostics for CP/M work include:

- instruction trace around a hang;
- I/O trace by port;
- IDE sector read/write trace;
- memory writes into protected ROM;
- configurable breakpoints at BIOS/BDOS entry points;
- dump of common-memory layout after boot;
- automatic capture of console output.

These features should be optional so normal CP/M execution remains fast and uncluttered.
