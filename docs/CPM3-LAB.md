# CP/M 3 Development Lab

One of the primary goals of this emulator is to make CP/M 3 system generation, BIOS development, and TPA optimization fast and repeatable.

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

When the CP/M boot path is operational, automate or at least standardize builds around candidate top-of-memory values such as:

```text
EB
EC
ED
EE
EF
F0
```

The exact valid range will be determined by the generated system and the fixed `F000H-FFFFH` ROM window. `F0` is a boundary check, not an assumption that CP/M may occupy ROM space.

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
8. repeat directory access after warm boot.

Later tests can cover file creation/deletion, larger sequential I/O, SUBMIT, and utilities used during system generation.

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
