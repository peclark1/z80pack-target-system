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

- Target System — 60K RAM at `0000H-EFFFH` plus the current 4K monitor ROM at `F000H-FFFFH`
- DSI Compatibility — full 64K RAM, no target ROM, automatic DSI bootstrap
- CPU speed in MHz
- IMSAI front-panel / sense-switch input byte returned by `IN FFH`

The monitor's current low-two-bit console convention is:

- `00` — Console I/O
- `01` — Serial I/O A
- `02` — MIO
- `03` — reserved/fallback

### IDE / CF

- CF0 image
- CF1 image
- one-click full-geometry work-copy creation
- IDE command trace

A CF work copy uses the same `tools/make_cf_workcopy.py` helper used by the command-line lab, preserving compact/archive source images and expanding the working image to the 8 MiB logical geometry. GUI-created work copies always receive a new filename and never overwrite an existing work image.

### Digital Systems FDC-1

- DSI drive A image
- DSI drive B image
- one-click working copies
- DSI bootstrap enable
- DSI writes
- DSI command trace

The GUI recognizes the FDC-1 single-density geometry as exactly 256,256 bytes (`77 x 26 x 128`). DSI writes remain off by default. Prefer selecting an archival image, clicking **Work Copy**, and only then enabling **Allow DSI writes**. GUI-created DSI work copies never overwrite an existing work image.

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

Disk images themselves are never copied into the configuration directory. Only their selected paths and GUI options are saved.

## Planned enhancements

The first version intentionally keeps the GUI thin and uses the existing Makefile/emulator interfaces. Useful future additions include:

- named saved machine profiles
- separate emulator trace/log view so tracing does not clutter the CP/M terminal
- ROM revision and SHA display
- disk SHA-256 on demand
- dedicated reset / boot-source actions
- graphical IMSAI sense-switch controls
- additional target devices as their emulation is implemented
