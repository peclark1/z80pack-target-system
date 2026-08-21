/* Software-visible emulation of the S100Computers Dual IDE/CF V3 board. */

#ifndef TARGET_IDE_INC
#define TARGET_IDE_INC

#include "simdefs.h"

extern void target_ide_init(void);
extern void target_ide_reset(void);
extern void target_ide_exit(void);

extern BYTE target_ide_a_in(void);
extern BYTE target_ide_b_in(void);
extern BYTE target_ide_c_in(void);

extern void target_ide_a_out(BYTE data);
extern void target_ide_b_out(BYTE data);
extern void target_ide_c_out(BYTE data);
extern void target_ide_ctrl_out(BYTE data);
extern void target_ide_drive_out(BYTE data);

#endif /* !TARGET_IDE_INC */
