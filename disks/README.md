# Local CF and Disk Images

Disk images are intentionally not committed to this repository.

For the Dual IDE/CF emulator, the default local filenames are:

```text
disks/cf0.img   first/master CF device
disks/cf1.img   second CF device
```

`make run` passes those paths to the emulator as `TARGET_CF0` and `TARGET_CF1`.
Alternative paths can be supplied without moving the images:

```sh
make run CF0=/path/to/drive-a.img CF1=/path/to/drive-b.img
```

Enable ATA command tracing with:

```sh
make run IDE_TRACE=1
```

The emulator opens an image read/write when permissions allow and falls back to read-only access otherwise. For CP/M system-generation experiments, prefer disposable copies of known-good CF images.

## Image interpretation

The current IDE model presents each file as a flat LBA-addressed ATA device with 512-byte sectors. LBA sector 0 begins at byte offset 0, sector 1 at byte offset 512, and so on.

The target monitor's IDE boot path reads 12 sectors beginning at LBA sector 1 into `0100H` and verifies that the first loader opcode is `31H` (`LD SP,nn`) before jumping to it.
