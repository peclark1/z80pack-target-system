# Altair FDC+ Drive Type 8 emulation

This target-device model emulates the **software-visible FDC+ interface when the physical FDC+ is configured for Drive Type 8**. In that configuration the FDC+ makes attached Shugart-compatible 8-inch drives look like an iCOM/Pertec FD3712 controller using IBM-3740 media.

This is intentionally **not** a full emulation of every FDC+ drive type. The immediate purpose is to run and diagnose the target CP/M 3 FDC+ path against the same FD3712 command protocol used by the physical machine.

## Software interface

The FDC+3712 implementation relocates the original FD3712 interface to the FDC+ default I/O base:

| Port | Direction | Type 8 meaning |
| --- | --- | --- |
| `08H` | IN | controller status or read-buffer data |
| `08H` | OUT | FD3712 command |
| `09H` | OUT | controller data latch |
| `0AH` | IN/OUT | not used by the Type 8 FD3712 protocol |
| `0BH` | IN/OUT | reserved |

When tracing is enabled, accesses to `0AH` or `0BH` are reported explicitly. This is useful when diagnosing a BIOS that is accidentally still using the normal MITS/Altair FDC register map rather than the Type 8 FD3712 protocol.

Implemented controller commands are:

- `00H` status mode
- `03H` read sector
- `05H` write sector
- `07H` read/validate CRC
- `09H` seek
- `0BH` clear errors
- `0DH` restore to track zero
- `11H` set requested track
- `15H` load configuration
- `21H` set drive and sector
- `31H` load write buffer
- `40H` read buffer
- `41H` shift read buffer
- `81H` controller reset

Status bits modeled are BUSY, seek error, CRC error, write protect, and not ready. Controller operations complete immediately in emulator time, so BUSY is clear when guest software polls after issuing a command.

## Media format

Type 8 images are flat IBM-3740 images:

- 77 tracks
- one side
- 26 sectors per track
- 128 bytes per sector
- sector IDs 1 through 26
- exact image size: **256,256 bytes**

The emulator rejects images of another size rather than guessing a geometry.

## Running with a Type 8 disk

Attach drive 0 and enable trace output:

```sh
make run \
  FDCPLUS0=/path/to/ibm3740.dsk \
  FDCPLUS_TRACE=1
```

Up to four Type 8 units can be attached:

```sh
make run \
  FDCPLUS0=/path/to/drive0.dsk \
  FDCPLUS1=/path/to/drive1.dsk \
  FDCPLUS_TRACE=1
```

The same session may also have the Dual IDE/CF devices attached. That is the intended CP/M 3 diagnostic setup: boot CP/M 3 from IDE/CF while exposing the FDC+ Type 8 drives to the CP/M BIOS.

## Write safety

FDC+ images are opened read-only by default. This is deliberate so archived floppy images cannot be modified accidentally.

For a disposable scratch image only, enable writes explicitly:

```sh
make run \
  FDCPLUS0=/path/to/scratch.dsk \
  FDCPLUS_WRITE=1 \
  FDCPLUS_TRACE=1
```

## Trace diagnostics

A healthy Type 8 path should produce operations such as:

```text
target-fdcplus8: DRIVE/SECTOR drive=0 sector=1
target-fdcplus8: SET TRACK 0
target-fdcplus8: drive=0 SEEK track=0 sector=1 status=10
target-fdcplus8: drive=0 READ track=0 sector=1 status=10
```

`10H` in a read-only session is the modeled write-protect status bit; it does not prevent reads.

If a BIOS uses the normal Altair register layout instead of the Type 8 FD3712 layout, tracing calls that out, for example:

```text
target-fdcplus8: IN 0A -> FF (Type 8 data/status is IN 08)
target-fdcplus8: OUT 0A,xx ignored (Type 8 data latch is OUT 09)
```

That makes the emulator useful as a protocol analyzer, not just as a disk-image backend.

## CP/M 3 integration

The current `feature/fdcplus-8in` CP/M 3 work uses the FDC+ services in the target 4K ROM. Those ROM services ultimately execute the native FD3712 command sequence at ports `08H/09H`, so the emulator model sits below the ROM API just as the physical FDC+ does.

This lets us distinguish several failure classes cleanly:

1. CP/M 3 adapter/DPH/DPB/sector-translation problems;
2. target-ROM API/workspace problems;
3. wrong FDC+ command or port usage;
4. incorrect track/sector requests;
5. missing/not-ready media;
6. write-protect behavior.

## Regression test

CI includes a small synthetic 4K ROM and IBM-3740 disk image. The ROM executes the FDC+3712 reset/select/restore/read/read-buffer/shift sequence through the targetsim I/O ports and must print `FDCPLUS8 OK` through Console I/O.

This verifies the Type 8 protocol independently of CP/M before using the emulator to diagnose the larger CP/M 3 build.

## Deliberate limitations

The current model does not simulate rotational timing, physical head-load delays, interrupt timing, flux-level errors, or soft-sector generation. It operates on flat logical sector images and makes controller commands complete immediately. Those details can be added later if software proves to depend on them; they are not needed for the current CP/M 3 BIOS/ROM debugging goal.
