# Digital Systems FDC-1 single-density support

The target emulator models the software-visible interface of the Digital Systems FDC-1 single-density controller used by the IMSAI's DSI 8-inch subsystem.

This is intentionally **not** the later FDC-3 model. There is no FDC-3 `7CH` command/density register and no double-density/M2FM support in this device.

## Supported media

The initial implementation accepts only flat raw IBM-3740-style single-density images with exactly this geometry:

- 77 tracks
- 1 side
- 26 sectors per track
- 128 bytes per sector
- 256,256 bytes total

Images with any other size are rejected. This is deliberate so that an FDC-3 mixed/double-density image cannot silently be interpreted as an FDC-1 disk.

DSI images are opened read-only by default. Set `DSI_WRITE=1` (which becomes `TARGET_DSI_WRITE=1` for targetsim) only when using a disposable scratch image.

## FDC-1 I/O map

| Port | Direction | Function |
| --- | --- | --- |
| `7DH` | OUT | DMA address low byte |
| `7EH` | IN | Invoke controller bootstrap: track 0 sector 1 -> `0000H-007FH` |
| `7EH` | OUT | DMA address high byte |
| `7FH` | IN | Controller status |
| `7FH` | OUT | Controller command |

The command register implements the direct FDC-1 convention used by the recovered single-density BIOS material:

- bit 0: file-inoperative reset
- bit 1: step
- bit 2: direction (`1` inward, `0` toward track 0)
- bit 3: enable drive-select latch
- bits 4-5: drive select
- bit 6: read
- bit 7: write

Status currently models the software-visible conditions required by the DSI BIOS:

- bit 0: file inoperative
- bit 1: step ready
- bit 2: track zero
- bit 3: I/O finish
- bit 4: track error
- bit 7: head unloaded/not ready

## Normal sector DMA

A normal read or write uses the FDC-1's 131-byte memory buffer format at the programmed DMA address:

```text
DMA+0    physical track
DMA+1    physical sector (1-26)
DMA+2    data address mark
DMA+3    first data byte
...
DMA+130  last data byte
```

For a read, the emulator writes `FBH` into `DMA+2` and the 128 sector bytes into `DMA+3..DMA+130`.

## Bootstrap behavior

The documented hardware bootstrap is different from a normal 131-byte operation. It reads track 0 sector 1 directly into `0000H-007FH` without CPU assistance.

Two paths are available:

1. `DSI_BOOTSTRAP=1` models the DSI bootstrap latch being active during controller reset/startup.
2. Guest software can execute `IN 7EH` to invoke the same bootstrap under program control.

The normal target-system profile still starts the North Star CPU at `F000H`; bootstrap mode only populates low RAM. This matches the useful physical behavior where the monitor can later execute the loader with `G0000`.

## Running with the physical target profile

Attach one or two DSI SD images while retaining the real target memory map and monitor ROM:

```sh
make run \
  DSI0=/path/to/drive-a.img \
  DSI1=/path/to/drive-b.img
```

To simulate the automatic DSI reset/bootstrap latch as well:

```sh
make run \
  DSI0=/path/to/drive-a.img \
  DSI_BOOTSTRAP=1
```

The target profile remains:

```text
0000H-EFFFH   60K RAM
F000H-FFFFH    4K target monitor ROM
reset/POJ      F000H
```

This profile is the one to use when checking whether historical DSI software can coexist with the target monitor.

## Historical 64K compatibility profile

Some archived CP/M systems were generated for more RAM than the target can expose below the `F000H` ROM window. In particular, a 61K CP/M system can use memory through approximately `F3FFH` and therefore collide with the target ROM.

For those images, use the isolated compatibility profile:

```sh
make dsi-compat DSI0=/path/to/single-density.img
```

That profile provides:

```text
0000H-FFFFH   64K RAM
no target ROM
DSI bootstrap enabled
execution begins at 0000H
```

This is a diagnostic/compatibility environment, not a claim about the physical target configuration. If an image boots here but fails in the normal target profile near the top of memory, the difference points to the 61K-vs-60K/ROM layout rather than the floppy-controller model.

## Tracing

Enable controller tracing with:

```sh
make dsi-compat DSI0=/path/to/disk.img DSI_TRACE=1
```

or with the target profile:

```sh
make run DSI0=/path/to/disk.img DSI_TRACE=1 DSI_BOOTSTRAP=1
```

Trace output includes image mounting, bootstrap activity, drive selection, stepping, DMA addresses, and sector reads/writes.

## Write safety

The default is read-only. To test writes, first make a disposable copy and then explicitly enable them:

```sh
cp archive.img scratch.img
make dsi-compat DSI0="$PWD/scratch.img" DSI_WRITE=1
```

## Automated regression

`make smoke` now performs two independent end-to-end boot tests:

1. the existing real target ROM -> Dual IDE/CF -> CPMLDR regression;
2. a generated 256,256-byte DSI SD disk whose track-0/sector-1 bootstrap uses the FDC-1 ports to DMA-read track 0 sector 2 and print `DSI FDC1 OK` through Console I/O.

The DSI regression therefore exercises the hardware bootstrap, drive selection, DMA address latches, command/status port, normal 131-byte sector DMA, and Console I/O integration.

## Current intentional limits

The first implementation does not attempt to emulate:

- FDC-3 `7CH` COMAND2 behavior
- double density or M2FM media
- analog data separator behavior or CRC timing
- exact rotational/head-unload timing
- electrical S-100 DMA arbitration timing

Those are unnecessary for the known FDC-1 single-density software path and can be added only if a real software compatibility case requires them.
