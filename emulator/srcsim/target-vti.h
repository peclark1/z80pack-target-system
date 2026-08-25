#ifndef TARGET_VTI_H
#define TARGET_VTI_H

#include "simdefs.h"

#define TARGET_VTI_BASE 0x8800
#define TARGET_VTI_SIZE 0x0400
#define TARGET_VTI_COLS 64
#define TARGET_VTI_ROWS 16

void target_vti_init(void);
void target_vti_reset(void);
void target_vti_exit(void);

BYTE target_vti_keyboard_data_in(void);
BYTE target_vti_keyboard_status_in(void);

#endif
