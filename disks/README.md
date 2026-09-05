# Local CF and Disk Images

Disk images are intentionally not committed to this repository.

## Emulator image library

The GTK GUI keeps emulator-specific master images under:

```text
disks/library/
    library.db
    masters/
        cf/
        floppy/
```

The entire `disks/library/` tree is ignored by Git. It is meant for personal images prepared for this emulator, not for archival copies of real media. Masters stored in the library are made read-only so selecting a master directly cannot accidentally modify the known-good copy; normal experiments should use a managed working copy.

The GUI's **Library…** button lets you add a master image with a profile and description, browse masters, and see the working copies derived from each master. **Work Copy** records that lineage instead of creating anonymous copies. If a master already has working copies, the library view lets you reuse one or explicitly create another. Existing `build/*work*.img` files that predate the library appear as **untracked** and can be used as-is or linked to a selected master once their origin is known.

**Reset from Master** restores a managed working copy from its master while preserving the working filename and its catalog record. CF resets continue to use the normal 8 MiB work-copy preparation logic; floppy resets are direct copies. **Delete Copy** removes an unwanted working image without touching its master.

Master paths and work-copy paths inside this checkout are stored relative to the repository root so the catalog stays portable if the checkout is moved.

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
