/*
 * Digital Systems FDC-1 single-density controller interface.
 *
 * Software-visible ports on the documented Altair-compatible interface:
 *   7Dh OUT  DMA address low byte
 *   7Eh OUT  DMA address high byte
 *   7Fh IN   status
 *   7Fh OUT  command
 *
 * The separate HB interface software-bootstrap/restart input associated with
 * IN 7Eh is intentionally not part of the initial secondary-disk model.
 */

#ifndef TARGET_DSI_FDC1_H
#define TARGET_DSI_FDC1_H

#include "sim.h"

void target_dsi_fdc1_init(void);
void target_dsi_fdc1_reset(void);
void target_dsi_fdc1_exit(void);

BYTE target_dsi_fdc1_status_in(void);
void target_dsi_fdc1_dma_low_out(BYTE data);
void target_dsi_fdc1_dma_high_out(BYTE data);
void target_dsi_fdc1_command_out(BYTE data);

#endif
