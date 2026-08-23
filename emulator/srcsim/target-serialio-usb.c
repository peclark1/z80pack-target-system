#define _XOPEN_SOURCE 600

#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

#include "simdefs.h"
#include "target-serialio-usb.h"

/*
 * Software-visible subset of the S100Computers Serial I/O V3 DLP-USB245R
 * interface used by HOST.COM.
 *
 *   AAH: USB FIFO handshake/status
 *        bit 7 = RXF/RX ready, active LOW
 *        bit 6 = TXE/TX ready, active LOW
 *   ACH: USB FIFO data
 *
 * The host side is a pseudo-terminal. pySerial opens the slave side just like
 * a USB serial device; the emulator owns the PTY master. Baud rate is ignored
 * because the DLP FIFO itself is byte-oriented from the Z80's point of view.
 */

#define RX_READY_MASK 0x80
#define TX_READY_MASK 0x40
#define DEFAULT_STATUS 0xff

static int usb_master_fd = -1;
static BYTE last_data;
static char *usb_link_path;
static int usb_link_created;

static char *default_link_path(void)
{
    char buffer[128];

    snprintf(buffer, sizeof(buffer), "/tmp/targets100sim-usb-%lu",
             (unsigned long) getuid());
    return strdup(buffer);
}

static int prepare_link_path(const char *path)
{
    struct stat st;

    if (lstat(path, &st) == -1)
        return errno == ENOENT ? 0 : -1;

    if (!S_ISLNK(st.st_mode) || st.st_uid != getuid()) {
        errno = EEXIST;
        return -1;
    }

    return unlink(path);
}

BYTE target_serialio_usb_status_in(void)
{
    struct pollfd pfd;
    BYTE status = DEFAULT_STATUS;

    if (usb_master_fd < 0)
        return status;

    /* The FIFO has room from the guest's perspective. If no host currently
     * has the PTY open, writes are simply dropped and HOST.COM will advertise
     * readiness again after a client connects.
     */
    status &= (BYTE) ~TX_READY_MASK;

    pfd.fd = usb_master_fd;
    pfd.events = POLLIN;
    pfd.revents = 0;
    if (poll(&pfd, 1, 0) > 0 && (pfd.revents & POLLIN))
        status &= (BYTE) ~RX_READY_MASK;

    return status;
}

BYTE target_serialio_usb_data_in(void)
{
    BYTE data;
    ssize_t count;

    if (usb_master_fd < 0)
        return last_data;

    count = read(usb_master_fd, &data, 1);
    if (count == 1) {
        last_data = data;
        return data;
    }

    return last_data;
}

void target_serialio_usb_data_out(BYTE data)
{
    ssize_t count;

    if (usb_master_fd < 0)
        return;

    do {
        count = write(usb_master_fd, &data, 1);
    } while (count < 0 && errno == EINTR);

    /* EIO means no slave/client is open; EAGAIN means its queue is full. Both
     * are transient and must not stop the emulator.
     */
}

void target_serialio_usb_init(void)
{
    const char *configured_path;
    char *slave_name;

    target_serialio_usb_exit();

    usb_master_fd = posix_openpt(O_RDWR | O_NOCTTY | O_NONBLOCK);
    if (usb_master_fd < 0) {
        fprintf(stderr, "Serial I/O USB: cannot allocate PTY: %s\n",
                strerror(errno));
        return;
    }

    if (grantpt(usb_master_fd) < 0 || unlockpt(usb_master_fd) < 0) {
        fprintf(stderr, "Serial I/O USB: cannot initialize PTY: %s\n",
                strerror(errno));
        close(usb_master_fd);
        usb_master_fd = -1;
        return;
    }

    slave_name = ptsname(usb_master_fd);
    if (slave_name == NULL) {
        fprintf(stderr, "Serial I/O USB: cannot locate PTY slave: %s\n",
                strerror(errno));
        close(usb_master_fd);
        usb_master_fd = -1;
        return;
    }

    configured_path = getenv("TARGET_SERIALIO_USB_TTY");
    if (configured_path != NULL && *configured_path != '\0')
        usb_link_path = strdup(configured_path);
    else
        usb_link_path = default_link_path();

    if (usb_link_path == NULL) {
        fprintf(stderr, "Serial I/O USB: out of memory creating PTY path\n");
        close(usb_master_fd);
        usb_master_fd = -1;
        return;
    }

    if (prepare_link_path(usb_link_path) < 0 ||
        symlink(slave_name, usb_link_path) < 0) {
        fprintf(stderr,
                "Serial I/O USB: cannot create %s -> %s: %s\n",
                usb_link_path, slave_name, strerror(errno));
        free(usb_link_path);
        usb_link_path = NULL;
        close(usb_master_fd);
        usb_master_fd = -1;
        return;
    }

    usb_link_created = 1;
    last_data = 0;
    fprintf(stderr, "Serial I/O USB: %s -> %s (ports AAh/ACh)\n",
            usb_link_path, slave_name);
}

void target_serialio_usb_reset(void)
{
    last_data = 0;
}

void target_serialio_usb_exit(void)
{
    if (usb_master_fd >= 0) {
        close(usb_master_fd);
        usb_master_fd = -1;
    }

    if (usb_link_created && usb_link_path != NULL)
        unlink(usb_link_path);

    free(usb_link_path);
    usb_link_path = NULL;
    usb_link_created = 0;
    last_data = 0;
}
