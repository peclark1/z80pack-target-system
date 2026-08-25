/*
 * Target-system I/O overlay for z80pack imsaisim.
 *
 * This file intentionally models only software-visible interfaces used by the
 * physical IMSAI target. Additional cards are added as the ROM/BIOS needs
 * them.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <unistd.h>

#include "sim.h"
#include "simdefs.h"
#include "simglb.h"
#include "simcfg.h"
#include "simio.h"

#include "imsai-sio2.h"
#include "imsai-hal.h"
#include "unix_network.h"
#include "target-ide.h"
#include "target-dsi-fdc1.h"
#include "target-fdcplus-type8.h"
#include "target-serialio-usb.h"
#include "target-vti.h"

/* The upstream IMSAI HAL expects the machine layer to supply the connector
 * array declared by simio.h. SIO2A uses element zero for the MIO socket.
 */
unix_connector_t ucons[NUMUSOC];

/* Optional live front-panel value file. The GTK front end writes a two-digit
 * hexadecimal byte here whenever a graphical sense switch moves. CLI sessions
 * continue to use TARGET_FP_PORT exactly as before when no file is supplied.
 */
static char *front_panel_value_file;

/* The modern target uses Console I/O V2 at 00H/01H. The restored historical
 * DSI/VTI workstation instead used the native IMSAI SIO channel A at 02H/03H,
 * with the SIO control register at 08H. TARGET_CONSOLE=sio selects that map.
 */
static int use_imsai_sio_console;

/*
 * Historical disk-head tester compatibility layer.
 *
 * The surviving BASIC suite establishes the interface much more precisely
 * than any surviving hardware documentation:
 *
 *   E0H-EBH  actuator, erase/write-current and test-control registers
 *   E8H      left status latch when read
 *   E9H      right status latch when read
 *   EEH-EFH  12-bit A/D converter
 *   FFH      IMSAI sense switches (handled separately below)
 *
 * Ports 02H/03H are NOT part of the fixture: surviving VID.HEX uses exactly
 * the normal IMSAI SIO handshake there (IN 03H transmitter-ready, OUT 02H
 * character). This matches the original workstation's printing terminal /
 * Teletype serving as both console and hard-copy output.
 *
 * This is intentionally a cooperative fixture model, not a magnetic-physics
 * simulator. It acknowledges moves/writes as complete and supplies repeatable
 * A/D readings for a healthy virtual head. The original BASIC program still
 * performs all amplitude, resolution, overwrite and pass/fail calculations.
 *
 * TARGET_HEADTEST_ENABLE can explicitly control the layer. If it is omitted,
 * the historical DSI+VTI profile enables it together with TARGET_VTI_ENABLE.
 */
static int headtester_enabled;
static BYTE headtester_regs[12];

static int env_flag(const char *name, int fallback)
{
    const char *value = getenv(name);

    if (value == NULL || *value == '\0')
        return fallback;
    return strcmp(value, "0") != 0 && strcasecmp(value, "false") != 0 &&
           strcasecmp(value, "no") != 0;
}

static void headtester_reset(void)
{
    memset(headtester_regs, 0, sizeof(headtester_regs));
}

static void headtester_init(void)
{
    headtester_enabled = env_flag(
        "TARGET_HEADTEST_ENABLE", env_flag("TARGET_VTI_ENABLE", 0));
    headtester_reset();
}

static void headtester_exit(void)
{
    headtester_enabled = 0;
}

#define HEADTEST_OUT_FN(name, port) \
    static void name(BYTE data) \
    { \
        if (headtester_enabled) \
            headtester_regs[(port) - 0xe0] = data; \
    }

HEADTEST_OUT_FN(headtester_e0_out, 0xe0)
HEADTEST_OUT_FN(headtester_e1_out, 0xe1)
HEADTEST_OUT_FN(headtester_e2_out, 0xe2)
HEADTEST_OUT_FN(headtester_e3_out, 0xe3)
HEADTEST_OUT_FN(headtester_e4_out, 0xe4)
HEADTEST_OUT_FN(headtester_e5_out, 0xe5)
HEADTEST_OUT_FN(headtester_e6_out, 0xe6)
HEADTEST_OUT_FN(headtester_e7_out, 0xe7)
HEADTEST_OUT_FN(headtester_e8_out, 0xe8)
HEADTEST_OUT_FN(headtester_e9_out, 0xe9)
HEADTEST_OUT_FN(headtester_ea_out, 0xea)
HEADTEST_OUT_FN(headtester_eb_out, 0xeb)

static BYTE headtester_left_status_in(void)
{
    /* TEST.BAS accepts 01H or 0BH for actuator completion and specifically
     * waits for 0BH after write operations. Always-ready 0BH exercises the
     * complete original state machine without adding arbitrary timing.
     */
    return headtester_enabled ? 0x0b : 0xff;
}

static BYTE headtester_right_status_in(void)
{
    return headtester_enabled ? 0x0b : 0xff;
}

static unsigned headtester_adc_value(void)
{
    BYTE control;

    if (!headtester_enabled)
        return 0x0fff;

    control = headtester_regs[0xe8 - 0xe0];

    /* RRGHT is bit 6 in TEST.BAS. The right read channel is used for the
     * overwrite measurement; 4050 produces a believable low-40-dB overwrite
     * result. Normal left-channel reads use 3800, which produces amplitudes
     * and 1F/2F resolution ratios comfortably inside INFO.LVL's limits while
     * still letting the BASIC code perform every calculation itself.
     */
    return (control & 0x40) ? 4050u : 3800u;
}

static BYTE headtester_adc_high_in(void)
{
    return (BYTE) ((headtester_adc_value() >> 8) & 0x0f);
}

static BYTE headtester_adc_low_in(void)
{
    return (BYTE) (headtester_adc_value() & 0xff);
}

/* Console I/O V2 uses different ready-bit positions than the IMSAI SIO
 * terminal backend we reuse. SIO1A reports TX=bit0/RX=bit1; the Console I/O
 * target expects TX=bit2/RX=bit1.
 */
static BYTE console_io_status_in(void)
{
    BYTE sio_status = imsai_sio1a_status_in();
    BYTE cio_status = 0;

    if (sio_status & 0x02)
        cio_status |= 0x02;      /* RX ready -> bit 1 */
    if (sio_status & 0x01)
        cio_status |= 0x04;      /* TX ready -> bit 2 */

    return cio_status;
}

/*
 * Ctrl-] (ASCII 1Dh) is reserved as the targetsim host escape key. Ctrl-C
 * remains a normal guest character so CP/M programs retain their historical
 * interrupt/abort behavior. Setting the normal z80pack USERINT state lets
 * run_cpu() unwind through mon(), which in turn restores the UNIX terminal.
 */
static BYTE terminal_data_in(void)
{
    BYTE data = imsai_sio1a_data_in();

    if (data == 0x1d) {
        cpu_error = USERINT;
        cpu_state = ST_STOPPED;
        return 0;
    }

    return data;
}

/* Runtime-dispatched low ports let one targetsim binary represent both the
 * current target and the historically accurate DSI/VTI workstation.
 */
static BYTE target_port00_in(void)
{
    return use_imsai_sio_console ? 0xff : console_io_status_in();
}

static BYTE target_port01_in(void)
{
    return use_imsai_sio_console ? 0xff : terminal_data_in();
}

static void target_port01_out(BYTE data)
{
    if (!use_imsai_sio_console)
        imsai_sio1a_data_out(data);
}

static BYTE target_port02_in(void)
{
    return use_imsai_sio_console ? terminal_data_in() : 0xff;
}

static void target_port02_out(BYTE data)
{
    if (use_imsai_sio_console)
        imsai_sio1a_data_out(data);
}

static BYTE target_port03_in(void)
{
    return use_imsai_sio_console ? imsai_sio1a_status_in() : 0xff;
}

static void target_port03_out(BYTE data)
{
    if (use_imsai_sio_console)
        imsai_sio1a_status_out(data);
}

/* Port 08H is FDC+ command/status in the modern target, but it is the IMSAI
 * SIO control register in the historical workstation. The two hardware
 * profiles are mutually exclusive, so runtime dispatch is unambiguous.
 */
static BYTE target_port08_in(void)
{
    return use_imsai_sio_console
        ? imsai_sio1_ctl_in()
        : target_fdcplus_type8_status_data_in();
}

static void target_port08_out(BYTE data)
{
    if (use_imsai_sio_console)
        imsai_sio1_ctl_out(data);
    else
        target_fdcplus_type8_command_out(data);
}

static void refresh_front_panel_from_file(void)
{
    FILE *stream;
    char buffer[32];
    char *end = NULL;
    long parsed;

    if (front_panel_value_file == NULL || *front_panel_value_file == '\0')
        return;

    stream = fopen(front_panel_value_file, "r");
    if (stream == NULL)
        return;

    if (fgets(buffer, sizeof(buffer), stream) != NULL) {
        parsed = strtol(buffer, &end, 16);
        if (end != buffer && parsed >= 0 && parsed <= 0xff)
            fp_port = (BYTE) parsed;
    }

    fclose(stream);
}

static BYTE front_panel_in(void)
{
    refresh_front_panel_from_file();
    return fp_port;
}

static void front_panel_out(BYTE data)
{
    UNUSED(data);
}

static void apply_runtime_overrides(void)
{
    const char *value = getenv("TARGET_FP_PORT");
    const char *file = getenv("TARGET_FP_FILE");
    const char *console = getenv("TARGET_CONSOLE");
    char *end = NULL;
    long parsed;

    use_imsai_sio_console = console != NULL &&
        (strcasecmp(console, "sio") == 0 ||
         strcasecmp(console, "imsai-sio") == 0);

    free(front_panel_value_file);
    front_panel_value_file = NULL;

    if (file != NULL && *file != '\0')
        front_panel_value_file = strdup(file);

    if (value != NULL && *value != '\0') {
        parsed = strtol(value, &end, 16);
        if (end != value && *end == '\0' && parsed >= 0 && parsed <= 0xff)
            fp_port = (BYTE) parsed;
    }

    /* If a live-value file already exists, let it override the fallback byte
     * immediately so the first IN FFH sees the GUI switch state.
     */
    refresh_front_panel_from_file();
}

/* Unused by the target overlay, but declared by the inherited IMSAI simio.h
 * and referenced by optional upstream web-front-end code.
 */
void lpt_reset(void)
{
}

/*
 * Port dispatch table.
 *
 * Unspecified entries are NULL. z80pack's core then returns IO_DATA_UNUSED
 * (FFH) for IN and ignores OUT unless I/O trapping is explicitly enabled.
 */
in_func_t *const port_in[256] = {
    [0x00] = target_port00_in,
    [0x01] = target_port01_in,
    [0x02] = target_port02_in,
    [0x03] = target_port03_in,

    /* 08H is runtime-dispatched between IMSAI SIO control and FDC+ status. */
    [0x08] = target_port08_in,
    [0x0a] = target_fdcplus_type8_port0a_in,
    [0x0b] = target_fdcplus_type8_port0b_in,

    /* S100Computers Dual IDE/CF V3 */
    [0x30] = target_ide_a_in,
    [0x31] = target_ide_b_in,
    [0x32] = target_ide_c_in,

    /* MIO SIO subset. z80pack SIO2A already has the target's
     * TX-ready bit0 / RX-ready bit1 status convention.
     */
    [0x42] = imsai_sio2a_data_in,
    [0x43] = imsai_sio2a_status_in,

    /* Digital Systems FDC-1. IN 7Eh requests bootstrap; IN 7Fh is status. */
    [0x7e] = target_dsi_fdc1_bootstrap_in,
    [0x7f] = target_dsi_fdc1_status_in,

    /* Original disk-head test fixture status and A/D converter. */
    [0xe8] = headtester_left_status_in,
    [0xe9] = headtester_right_status_in,
    [0xee] = headtester_adc_high_in,
    [0xef] = headtester_adc_low_in,

    /* Serial I/O V3 DLP-USB245R FIFO used by HOST.COM. */
    [0xaa] = target_serialio_usb_status_in,
    [0xac] = target_serialio_usb_data_in,

    [0xff] = front_panel_in
};

out_func_t *const port_out[256] = {
    [0x01] = target_port01_out,
    [0x02] = target_port02_out,
    [0x03] = target_port03_out,

    /* 08H is runtime-dispatched between IMSAI SIO control and FDC+ command. */
    [0x08] = target_port08_out,
    [0x09] = target_fdcplus_type8_data_out,
    [0x0a] = target_fdcplus_type8_port0a_out,
    [0x0b] = target_fdcplus_type8_port0b_out,

    /* S100Computers Dual IDE/CF V3 */
    [0x30] = target_ide_a_out,
    [0x31] = target_ide_b_out,
    [0x32] = target_ide_c_out,
    [0x33] = target_ide_ctrl_out,
    [0x34] = target_ide_drive_out,

    [0x42] = imsai_sio2a_data_out,
    [0x43] = imsai_sio2a_status_out,

    /* Digital Systems FDC-1 single-density interface. */
    [0x7d] = target_dsi_fdc1_dma_low_out,
    [0x7e] = target_dsi_fdc1_dma_high_out,
    [0x7f] = target_dsi_fdc1_command_out,

    /* Original disk-head test fixture outputs. */
    [0xe0] = headtester_e0_out,
    [0xe1] = headtester_e1_out,
    [0xe2] = headtester_e2_out,
    [0xe3] = headtester_e3_out,
    [0xe4] = headtester_e4_out,
    [0xe5] = headtester_e5_out,
    [0xe6] = headtester_e6_out,
    [0xe7] = headtester_e7_out,
    [0xe8] = headtester_e8_out,
    [0xe9] = headtester_e9_out,
    [0xea] = headtester_ea_out,
    [0xeb] = headtester_eb_out,

    /* Serial I/O V3 DLP-USB245R FIFO used by HOST.COM. */
    [0xac] = target_serialio_usb_data_out,

    [0xff] = front_panel_out
};

void init_io(void)
{
    apply_runtime_overrides();
    imsai_sio_reset();
    hal_reset();
    target_ide_init();
    target_dsi_fdc1_init();
    target_fdcplus_type8_init();
    target_serialio_usb_init();
    target_vti_init();
    headtester_init();

    /* SIO2A/MIO backend: a local UNIX-domain socket. */
    init_unix_server_socket(&ucons[0], "targets100sim.mio");
}

void reset_io(void)
{
    imsai_sio_reset();
    target_ide_reset();
    target_dsi_fdc1_reset();
    target_fdcplus_type8_reset();
    target_serialio_usb_reset();
    target_vti_reset();
    headtester_reset();
}

void exit_io(void)
{
    int i;

    headtester_exit();
    target_vti_exit();
    target_serialio_usb_exit();
    target_fdcplus_type8_exit();
    target_dsi_fdc1_exit();
    target_ide_exit();

    free(front_panel_value_file);
    front_panel_value_file = NULL;

    for (i = 0; i < NUMUSOC; i++) {
        if (ucons[i].ssc)
            close(ucons[i].ssc);
    }
}
