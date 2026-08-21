/*
 * Target-system I/O overlay for z80pack imsaisim.
 *
 * This file intentionally models only software-visible interfaces used by the
 * physical IMSAI target. Additional cards are added as the ROM/BIOS needs
 * them.
 */

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

/* The upstream IMSAI HAL expects the machine layer to supply the connector
 * array declared by simio.h. SIO2A uses element zero for the MIO socket.
 */
unix_connector_t ucons[NUMUSOC];

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
 * Ctrl-] (ASCII 1Dh) is reserved as the targetsim host escape key.  Ctrl-C
 * remains a normal guest character so CP/M programs retain their historical
 * interrupt/abort behavior.  Setting the normal z80pack USERINT state lets
 * run_cpu() unwind through mon(), which in turn restores the UNIX terminal.
 */
static BYTE console_io_data_in(void)
{
    BYTE data = imsai_sio1a_data_in();

    if (data == 0x1d) {
        cpu_error = USERINT;
        cpu_state = ST_STOPPED;
        return 0;
    }

    return data;
}

static BYTE front_panel_in(void)
{
    return fp_port;
}

static void front_panel_out(BYTE data)
{
    UNUSED(data);
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
    [0x00] = console_io_status_in,
    [0x01] = console_io_data_in,

    /* S100Computers Dual IDE/CF V3 */
    [0x30] = target_ide_a_in,
    [0x31] = target_ide_b_in,
    [0x32] = target_ide_c_in,

    /* MIO SIO subset. z80pack SIO2A already has the target's
     * TX-ready bit0 / RX-ready bit1 status convention.
     */
    [0x42] = imsai_sio2a_data_in,
    [0x43] = imsai_sio2a_status_in,

    /* Digital Systems FDC-1: status shares 7Fh with command output. */
    [0x7f] = target_dsi_fdc1_status_in,

    [0xff] = front_panel_in
};

out_func_t *const port_out[256] = {
    [0x01] = imsai_sio1a_data_out,

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

    [0xff] = front_panel_out
};

void init_io(void)
{
    imsai_sio_reset();
    hal_reset();
    target_ide_init();
    target_dsi_fdc1_init();

    /* SIO2A/MIO backend: a local UNIX-domain socket. */
    init_unix_server_socket(&ucons[0], "targets100sim.mio");
}

void reset_io(void)
{
    imsai_sio_reset();
    target_ide_reset();
    target_dsi_fdc1_reset();
}

void exit_io(void)
{
    int i;

    target_dsi_fdc1_exit();
    target_ide_exit();

    for (i = 0; i < NUMUSOC; i++) {
        if (ucons[i].ssc)
            close(ucons[i].ssc);
    }
}
