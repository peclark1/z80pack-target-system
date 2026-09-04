/*
 * Polymorphic Systems Video Terminal Interface (VTI) overlay.
 *
 * The VTI exposes 1 KB of memory-mapped display RAM on any 1 KB boundary.
 * The keyboard input port follows the high byte of that display base. The
 * restored workstation historically used F800H-FBFFH / port F8H, while the
 * dedicated FDC+/VTI CP/M profile uses FC00H-FFFFH / port FCH so CP/M has one
 * contiguous 63K RAM region below video memory.
 *
 * TARGET_VTI_ENABLE=1 enables the device.
 * TARGET_VTI_BASE selects the display base (default F800H).
 * TARGET_VTI_SCREEN names the 1024-byte shared display file.
 * TARGET_VTI_KBD names a FIFO written by the GTK front end.
 * TARGET_VTI_VI selects the S-100 vectored-interrupt line VI0-VI7 used by the
 * VTI keyboard strobe. The North Star ZPB converts that VI level to the
 * corresponding 8080 RST instruction during interrupt acknowledge. Omit it to
 * leave keyboard interrupts disabled.
 */

#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

#include "sim.h"
#include "simdefs.h"
#include "simglb.h"
#include "simmem.h"
#include "target-vti.h"

#define VTI_PAGE_COUNT (TARGET_VTI_SIZE >> 8)

static int vti_enabled;
static unsigned vti_base = TARGET_VTI_DEFAULT_BASE;
static BYTE vti_keyboard_port = (TARGET_VTI_DEFAULT_BASE >> 8);
static int vti_vi = -1;

static int screen_fd = -1;
static BYTE *screen_map;
static BYTE *saved_rdrvec[VTI_PAGE_COUNT];
static BYTE *saved_wrtvec[VTI_PAGE_COUNT];
static int vectors_saved;

static char *keyboard_path;
static int keyboard_fd = -1;
static pthread_t keyboard_thread;
static int keyboard_thread_started;
static volatile int keyboard_stop;
static volatile BYTE keyboard_latch;

static int env_enabled(const char *name)
{
    const char *value = getenv(name);

    if (value == NULL || *value == '\0')
        return 0;
    return strcmp(value, "0") != 0 && strcasecmp(value, "false") != 0 &&
           strcasecmp(value, "no") != 0;
}

static char *default_path(const char *leaf)
{
    char buffer[256];

    snprintf(buffer, sizeof(buffer), "/tmp/targets100sim-%s-%lu",
             leaf, (unsigned long) getuid());
    return strdup(buffer);
}

static void configure_vti(void)
{
    const char *base_text = getenv("TARGET_VTI_BASE");
    const char *vi_text = getenv("TARGET_VTI_VI");
    char *end = NULL;
    unsigned long value;

    vti_base = TARGET_VTI_DEFAULT_BASE;
    vti_vi = -1;

    if (base_text != NULL && *base_text != '\0') {
        value = strtoul(base_text, &end, 0);
        if (end != base_text && *end == '\0' && value <= 0xfc00 &&
            (value & (TARGET_VTI_SIZE - 1)) == 0)
            vti_base = (unsigned) value;
        else
            fprintf(stderr,
                    "target-vti: invalid TARGET_VTI_BASE '%s'; using %04XH\n",
                    base_text, TARGET_VTI_DEFAULT_BASE);
    }
    vti_keyboard_port = (BYTE) (vti_base >> 8);

    if (vi_text != NULL && *vi_text != '\0') {
        end = NULL;
        value = strtoul(vi_text, &end, 0);
        if (end != vi_text && *end == '\0' && value <= 7)
            vti_vi = (int) value;
        else
            fprintf(stderr,
                    "target-vti: invalid TARGET_VTI_VI '%s'; interrupts disabled\n",
                    vi_text);
    }
}

static void map_vti_pages(void)
{
    unsigned first_page = vti_base >> 8;
    int page;

    if (!vti_enabled || screen_map == NULL)
        return;

    if (!vectors_saved) {
        for (page = 0; page < VTI_PAGE_COUNT; page++) {
            saved_rdrvec[page] = rdrvec[first_page + page];
            saved_wrtvec[page] = wrtvec[first_page + page];
        }
        vectors_saved = 1;
    }

    for (page = 0; page < VTI_PAGE_COUNT; page++) {
        rdrvec[first_page + page] = screen_map + (page << 8);
        wrtvec[first_page + page] = screen_map + (page << 8);
        p_tab[first_page + page] = MEM_RW;
    }
}

static void restore_vti_pages(void)
{
    unsigned first_page = vti_base >> 8;
    int page;

    if (!vectors_saved)
        return;

    for (page = 0; page < VTI_PAGE_COUNT; page++) {
        rdrvec[first_page + page] = saved_rdrvec[page];
        wrtvec[first_page + page] = saved_wrtvec[page];
    }
    vectors_saved = 0;
}

static int init_screen(void)
{
    const char *configured = getenv("TARGET_VTI_SCREEN");
    char *path = NULL;
    void *mapped;

    if (configured == NULL || *configured == '\0') {
        path = default_path("vti-screen");
        configured = path;
    }

    screen_fd = open(configured, O_RDWR | O_CREAT | O_TRUNC, 0600);
    free(path);
    if (screen_fd < 0)
        return -1;

    if (ftruncate(screen_fd, TARGET_VTI_SIZE) < 0)
        return -1;

    mapped = mmap(NULL, TARGET_VTI_SIZE, PROT_READ | PROT_WRITE,
                  MAP_SHARED, screen_fd, 0);
    if (mapped == MAP_FAILED)
        return -1;

    screen_map = mapped;

    /* Bit 7 selects character mode. A0H is therefore an ASCII space. */
    memset(screen_map, 0xa0, TARGET_VTI_SIZE);
    msync(screen_map, TARGET_VTI_SIZE, MS_ASYNC);
    return 0;
}

static void request_keyboard_interrupt(void)
{
    if (vti_vi < 0)
        return;

    /* The VTI manual provides a JMP2 pad for direct connection to any S-100
     * VI0-VI7 line. The North Star ZPB latches those lines during interrupt
     * acknowledge and supplies the corresponding RST instruction itself.
     * Therefore VI n is represented here as RST n: C7H + 8*n. The dedicated
     * profile uses VI2, which enters at 0010H. No PIC-8 is involved.
     */
    int_data = 0xc7 + (vti_vi << 3);
    int_int = true;
}

static void *keyboard_worker(void *unused)
{
    struct pollfd pfd;
    BYTE data[32];
    ssize_t count;
    ssize_t i;

    UNUSED(unused);
    pfd.fd = keyboard_fd;
    pfd.events = POLLIN;

    while (!keyboard_stop) {
        if (poll(&pfd, 1, 50) <= 0)
            continue;

        count = read(keyboard_fd, data, sizeof(data));
        if (count < 0) {
            if (errno == EAGAIN || errno == EINTR)
                continue;
            break;
        }

        for (i = 0; i < count; i++) {
            keyboard_latch = data[i] & 0x7f;
            request_keyboard_interrupt();
        }
    }

    return NULL;
}

static int init_keyboard(void)
{
    const char *configured = getenv("TARGET_VTI_KBD");
    struct stat st;

    if (configured == NULL || *configured == '\0')
        return 0;

    keyboard_path = strdup(configured);
    if (keyboard_path == NULL)
        return -1;

    if (lstat(keyboard_path, &st) == 0 && !S_ISFIFO(st.st_mode)) {
        if (unlink(keyboard_path) < 0)
            return -1;
    }
    if (mkfifo(keyboard_path, 0600) < 0 && errno != EEXIST)
        return -1;

    /* O_RDWR keeps a reader present so the GUI can open its nonblocking
     * write end even before the guest has enabled interrupts.
     */
    keyboard_fd = open(keyboard_path, O_RDWR | O_NONBLOCK);
    if (keyboard_fd < 0)
        return -1;

    keyboard_latch = 0;
    keyboard_stop = 0;
    if (pthread_create(&keyboard_thread, NULL, keyboard_worker, NULL) != 0)
        return -1;
    keyboard_thread_started = 1;
    return 0;
}

static BYTE keyboard_in_for_port(BYTE port)
{
    if (!vti_enabled || port != vti_keyboard_port)
        return 0xff;
    return keyboard_latch;
}

BYTE target_vti_keyboard_88_in(void)
{
    return keyboard_in_for_port(0x88);
}

BYTE target_vti_keyboard_f8_in(void)
{
    return keyboard_in_for_port(0xf8);
}

BYTE target_vti_keyboard_fc_in(void)
{
    return keyboard_in_for_port(0xfc);
}

void target_vti_init(void)
{
    vti_enabled = env_enabled("TARGET_VTI_ENABLE");
    if (!vti_enabled)
        return;

    configure_vti();

    if (init_screen() < 0) {
        fprintf(stderr, "target-vti: unable to initialize VTI shared display\n");
        target_vti_exit();
        return;
    }

    map_vti_pages();

    if (init_keyboard() < 0) {
        fprintf(stderr, "target-vti: unable to initialize keyboard FIFO\n");
        target_vti_exit();
        return;
    }

    if (vti_vi >= 0)
        fprintf(stderr,
                "target-vti: display %04XH-%04XH keyboard port %02XH via ZPB VI%d/RST %d\n",
                vti_base, vti_base + TARGET_VTI_SIZE - 1, vti_keyboard_port,
                vti_vi, vti_vi);
    else
        fprintf(stderr,
                "target-vti: display %04XH-%04XH keyboard port %02XH\n",
                vti_base, vti_base + TARGET_VTI_SIZE - 1, vti_keyboard_port);
}

void target_vti_reset(void)
{
    if (vti_enabled)
        map_vti_pages();
}

void target_vti_exit(void)
{
    restore_vti_pages();

    keyboard_stop = 1;
    if (keyboard_thread_started) {
        pthread_join(keyboard_thread, NULL);
        keyboard_thread_started = 0;
    }
    if (keyboard_fd >= 0) {
        close(keyboard_fd);
        keyboard_fd = -1;
    }
    if (keyboard_path != NULL) {
        unlink(keyboard_path);
        free(keyboard_path);
        keyboard_path = NULL;
    }

    if (screen_map != NULL) {
        msync(screen_map, TARGET_VTI_SIZE, MS_SYNC);
        munmap(screen_map, TARGET_VTI_SIZE);
        screen_map = NULL;
    }
    if (screen_fd >= 0) {
        close(screen_fd);
        screen_fd = -1;
    }

    vti_enabled = 0;
    vti_vi = -1;
}
