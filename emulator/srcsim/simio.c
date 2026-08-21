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
#include "simcfg.h"
#include "simio.h"

#include "imsai-sio2.h"
#include "imsai-hal.h"
#include "unix_network.h"

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
    [0x01] = imsai_sio1a_data_in,

    /* MIO SIO subset. z80pack SIO2A already has the target's
     * TX-ready bit0 / RX-ready bit1 status convention.
     */
    [0x42] = imsai_sio2a_data_in,
    [0x43] = imsai_sio2a_status_in,

    [0xFF] = front_panel_in
};

out_func_t *const port_out[256] = {
    [0x01] = imsai_sio1a_data_out,

    [0x42] = imsai_sio2a_data_out,
    [0x43] = imsai_sio2a_status_out,

    [0xFF] = front_panel_out
};

void init_io(void)
{
    imsai_sio_reset();
    hal_reset();

    /* SIO2A/MIO backend: a local UNIX-domain socket. */
    init_unix_server_socket(&ucons[0], "targets100sim.mio");
}

void reset_io(void)
{
    imsai_sio_reset();
}

void exit_io(void)
{
    int i;

    for (i = 0; i < NUMUSOC; i++) {
        if (ucons[i].ssc)
            close(ucons[i].ssc);
    }
}
