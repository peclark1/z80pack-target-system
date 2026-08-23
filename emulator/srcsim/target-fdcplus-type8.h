/*
 * Altair FDC+ Drive Type 8 (iCOM/Pertec FD3712) interface.
 *
 * FDC+ Type 8 relocates the software-visible FD3712 interface from its
 * original C0h/C1h addresses to the FDC+ default base address:
 *   08h IN   controller status / read-buffer data
 *   08h OUT  controller command
 *   09h OUT  controller data latch
 *
 * The remaining FDC+ decoded ports (0Ah/0Bh) are not used by the Type 8
 * FD3712 protocol. They are handled only so trace mode can flag accidental
 * use of the normal Altair hard-sector register map while Type 8 is active.
 */

#ifndef TARGET_FDCPLUS_TYPE8_H
#define TARGET_FDCPLUS_TYPE8_H

#include "sim.h"

void target_fdcplus_type8_init(void);
void target_fdcplus_type8_reset(void);
void target_fdcplus_type8_exit(void);

BYTE target_fdcplus_type8_status_data_in(void);
void target_fdcplus_type8_command_out(BYTE data);
void target_fdcplus_type8_data_out(BYTE data);

BYTE target_fdcplus_type8_port0a_in(void);
void target_fdcplus_type8_port0a_out(BYTE data);
BYTE target_fdcplus_type8_port0b_in(void);
void target_fdcplus_type8_port0b_out(BYTE data);

#endif
