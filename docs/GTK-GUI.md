# GTK4 front end

`gui/app.py` is a native Ubuntu GTK4 front end for the target-system emulator. It embeds a VTE terminal, so the CP/M console remains a real pseudo-terminal instead of being simulated by GUI text controls.

## Ubuntu dependencies

On Ubuntu 24.04 and later:

```sh
make gui-deps
```

This installs the Python GObject bindings, GTK4, the GTK4 VTE introspection package, and desktop-file utilities.

The equivalent package command is:

```sh
sudo apt install \
  python3-gi \
  python3-gi-cairo \
  gir1.2-gtk-4.0 \
  gir1.2-vte-3.91 \
  desktop-file-utils
```

## Launch from the checkout

```sh
make gui
```

The GUI calls the same Makefile targets used by command-line sessions. The live command preview in the window shows the exact `make run` or `make dsi-compat` command that will be executed.

## Install as an Ubuntu application

```sh
make gui-install
```

This is a per-user installation; it does not require root. It creates:

- `~/.local/bin/imsai-target-system`
- `~/.local/share/applications/com.peclark.z80pack-target-system.desktop`

The launcher intentionally points back to the current Git checkout, so a future `git pull` updates the installed application immediately without a reinstall.

Open Ubuntu's Applications view, search for **IMSAI Target System**, then right-click it and choose **Add to Favorites** to pin it to the Ubuntu dock/quick-launch bar.

To remove the launcher:

```sh
make gui-uninstall
```

Saved GUI settings under `~/.config/z80pack-target-system/gui.json` are retained by uninstall.

## Current controls

### Machine

- Target System — 60K RAM at `0000H-EFFFH` plus a selected 4K ROM at `F000H-FFFFH`
- DSI Compatibility — full 64K RAM, no target ROM, automatic DSI bootstrap
- CPU speed in MHz
- IMSAI front-panel / sense-switch input byte returned by `IN FFH`

### 4K ROM selection

Target System mode includes a **4K ROM @ F000H** selector. Leaving it blank, or pressing **Use Current**, uses the pinned/current ROM produced as `build/target-monitor.hex`.

**Browse…** accepts either:

- an exact 4096-byte logical ROM binary, or
- Intel HEX containing exactly `F000H-FFFFH`

The GUI validates the selected image and displays a short SHA-256 identifier. The source image is never modified. At launch, the selected ROM is normalized and staged as `build/run-rom/target-monitor.hex`; targetsim is pointed at that isolated directory for the session. Returning to **Use Current** immediately restores the normal pinned-ROM behavior.

The same capability is available from the command line:

```sh
make run ROM_IMAGE=/path/to/alternate-4k.bin
```

or:

```sh
make run ROM_IMAGE=/path/to/alternate-4k.hex
```

ROM selection is disabled in DSI Compatibility mode because that profile intentionally provides full 64K RAM with no ROM window.

### Graphical IMSAI sense switches

The Machine section includes an eight-switch graphical bank labeled bits 7 through 0. **UP = 1** and **DOWN = 0**. The switches and the hexadecimal `Front panel FFH` field are bidirectionally synchronized, so either can be used to set the byte.

The GUI also decodes the low two bits using the target monitor convention:

- `00` — Console I/O
- `01` — Serial I/O A
- `02` — MIO SIO
- `03` — reserved / Console I/O fallback

Graphical switch changes are live while targetsim is running. The GUI writes the current byte to `build/gui-front-panel.hex`, passes that file to targetsim with `FP_FILE=...`, and the target I/O layer refreshes the value on each `IN FFH`. A restart is therefore not required merely to move a sense switch. `FP_PORT=xx` remains the normal command-line fallback/default when no live file is supplied.

For command-line experiments the same live mechanism can be used directly:

```sh
printf '02\n' > /tmp/imsai-ff.hex
make run FP_PORT=00 FP_FILE=/tmp/imsai-ff.hex
```

Changing `/tmp/imsai-ff.hex` to another hexadecimal byte changes what subsequent `IN FFH` instructions read.

### IDE / CF

- CF0 image
- CF1 image
- one-click full-geometry work-copy creation
- IDE command trace

A CF work copy uses the same `tools/make_cf_workcopy.py` helper used by the command-line lab, preserving compact/archive source images and expanding the working image to the 8 MiB logical geometry. GUI-created work copies always receive a new filename and never overwrite an existing work image.

### Floppy controller selection

The **Floppy controller** selector makes the two emulated 8-inch controller families mutually exclusive. Its choices are:

- **None — IDE/CF only**
- **Digital Systems FDC-1**
- **Altair FDC+ — Type 8 / iCOM 3712**

Only the selected controller's settings panel expands. The other controller remains collapsed and is not attached to targetsim, even if image paths are still remembered in its controls. This makes it safe to switch back and forth without having to reselect images while guaranteeing that DSI and FDC+ are never active in the same GUI-launched session.

DSI Compatibility mode inherently requires the DSI FDC-1. In that profile the selector is disabled and the DSI panel is forced open. Returning to Target System mode restores the previous Target System floppy-controller choice.

### Digital Systems FDC-1

When **Digital Systems FDC-1** is selected, the expanded panel provides:

- DSI drive A image
- DSI drive B image
- one-click working copies
- DSI bootstrap enable
- DSI writes
- DSI command trace

The DSI FDC-1 single-density format is exactly 256,256 bytes (`77 x 26 x 128`). That byte size is also the flat IBM-3740 geometry used by FDC+ Type 8, so the generic image-info line identifies such files as IBM-3740 rather than guessing which controller they belong to. The selected controller determines how the image is interpreted.

DSI writes remain off by default. Prefer selecting an archival image, clicking **Work Copy**, and only then enabling **Allow DSI writes**. GUI-created DSI work copies never overwrite an existing work image.

### Altair FDC+ — Type 8 / iCOM 3712

When **Altair FDC+ — Type 8 / iCOM 3712** is selected in Target System mode, the expanded panel exposes all four Type 8 units supported by the emulator:

- FDC+ Drive 0 through Drive 3 image selectors
- one-click Type 8 working copies
- **Allow FDC+ writes**, off by default
- **FDC+ command trace**

Each Type 8 image must be an exact 256,256-byte IBM-3740 image (`77 tracks x 26 sectors x 128 bytes`). The GUI validates that size before launch. A **Work Copy** creates a new disposable image under `build/` with an `fdcplusN-gui-work...img` name, leaving the selected source untouched.

Even a work copy is attached read-only to the emulated FDC+ until **Allow FDC+ writes** is explicitly enabled. Write permission is deliberately not persisted across GUI launches. The same safety rule applies to DSI writes.

## Session controls

- **Build / Update** — incrementally build targetsim and the current monitor ROM
- **Start** — launch the selected configuration in the embedded VTE terminal
- **Restart** — cleanly stop and relaunch the current configuration
- **Stop** — sends the targetsim host escape, Ctrl-], so z80pack restores the terminal normally

Ctrl-C remains available to CP/M applications.

## Settings

The last GUI configuration is stored in:

```text
~/.config/z80pack-target-system/gui.json
```

Window size/maximized/divider state is stored separately in:

```text
~/.config/z80pack-target-system/window.json
```

Disk and ROM images themselves are never copied into the configuration directory. Only their selected paths and GUI options are saved. Disk write authorization is never persisted. On GTK4/Wayland, absolute top-level X/Y window placement remains compositor-managed.

Older GUI settings that predate the floppy-controller selector are migrated automatically: an existing FDC+ image selects FDC+; otherwise an existing DSI image selects DSI; otherwise the controller defaults to None.

## Planned enhancements

The GUI intentionally remains a thin front end over the existing Makefile/emulator interfaces. Useful future additions include:

- named saved machine profiles
- separate emulator trace/log view so tracing does not clutter the CP/M terminal
- richer ROM revision/build metadata for the pinned firmware
- disk SHA-256 on demand
- dedicated reset / boot-source actions
- a more complete IMSAI front-panel visualization beyond the sense-switch bank
- additional target devices as their emulation is implemented
