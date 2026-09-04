#ifndef TARGET_VTI_H
#define TARGET_VTI_H

#include "simdefs.h"

#define TARGET_VTI_DEFAULT_BASE 0xf800
#define TARGET_VTI_SIZE 0x0400
#define TARGET_VTI_COLS 64
#define TARGET_VTI_ROWS 16

void target_vti_init(void);
void target_vti_reset(void);
void target_vti_exit(void);

/* The VTI keyboard port is the high byte of the selected 1K display base.
 * These wrappers let the static z80pack I/O table expose the mappings used by
 * our profiles while target-vti.c decides which one is active at runtime.
 * Keyboard strobe interrupts are modeled separately as direct S-100 VI inputs
 * to the North Star ZPB's onboard vectored-interrupt logic.
 */
BYTE target_vti_keyboard_88_in(void);
BYTE target_vti_keyboard_f8_in(void);
BYTE target_vti_keyboard_fc_in(void);

#endif
