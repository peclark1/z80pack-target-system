#ifndef TARGET_SERIALIO_USB_H
#define TARGET_SERIALIO_USB_H

#include "simdefs.h"

BYTE target_serialio_usb_status_in(void);
BYTE target_serialio_usb_data_in(void);
void target_serialio_usb_data_out(BYTE data);
void target_serialio_usb_init(void);
void target_serialio_usb_reset(void);
void target_serialio_usb_exit(void);

#endif
