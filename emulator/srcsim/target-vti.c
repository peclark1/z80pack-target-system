/*
 * Polymorphic Systems Video Terminal Interface (VTI) overlay.
 *
 * The historical non-Poly-88 convention maps the 1 KB VTI display RAM at
 * 8800H-8BFFH. The upper byte of that address selects the keyboard ports:
 * 88H/8AH return keyboard data and 89H/8BH return keyboard status.
 *
 * TARGET_VTI_ENABLE=1 enables the device. TARGET_VTI_SCREEN names a 1024-byte
 * shared file used by the GTK front end, while TARGET_VTI_KBD names a FIFO
 * into which the front end writes 7-bit keyboard bytes.
 */

#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

#include "sim.h"
#include "simdefs.h"
#include "simglb.h"
#include "simmem.h"
#include "target-vti.h"

#define VTI_FIRST_PAGE (TARGET_VTI_BASE >> 8)
#define VTI_PAGE_COUNT (TARGET_VTI_SIZE >> 8)
#define VTI_IDLE_STATUS 0x81
#define VTI_PENDING_STATUS 0x00

static int vti_enabled;
static int screen_fd = -1;
static BYTE *screen_map;
static BYTE *saved_rdrvec[VTI_PAGE_COUNT];
static BYTE *saved_wrtvec[VTI_PAGE_COUNT];
static int vectors_saved;

static int keyboard_fd = -1;
static char *keyboard_path;
static pthread_t keyboard_thread;
static int keyboard_thread_started;
static volatile int keyboard_running;
static pthread_mutex_t keyboard_lock = PTHREAD_MUTEX_INITIALIZER;
static BYTE keyboard_data;
static int keyboard_pending;

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

static void map_vti_pages(void)
{
    int page;

    if (!vti_enabled || screen_map == NULL)
        return;

    if (!vectors_saved) {
        for (page = 0; page < VTI_PAGE_COUNT; page++) {
            saved_rdrvec[page] = rdrvec[VTI_FIRST_PAGE + page];
            saved_wrtvec[page] = wrtvec[VTI_FIRST_PAGE + page];
        }
        vectors_saved = 1;
    }

    for (page = 0; page < VTI_PAGE_COUNT; page++) {
        rdrvec[VTI_FIRST_PAGE + page] = screen_map + (page << 8);
        wrtvec[VTI_FIRST_PAGE + page] = screen_map + (page << 8);
        p_tab[VTI_FIRST_PAGE + page] = MEM_RW;
    }
}

static void restore_vti_pages(void)
{
    int page;

    if (!vectors_saved)
        return;

    for (page = 0; page < VTI_PAGE_COUNT; page++) {
        rdrvec[VTI_FIRST_PAGE + page] = saved_rdrvec[page];
        wrtvec[VTI_FIRST_PAGE + page] = saved_wrtvec[page];
    }
    vectors_saved = 0;
}

static void *keyboard_worker(void *unused)
{
    BYTE value;
    ssize_t count;

    UNUSED(unused);

    while (keyboard_running) {
        pthread_mutex_lock(&keyboard_lock);
        if (keyboard_pending) {
            pthread_mutex_unlock(&keyboard_lock);
            usleep(1000);
            continue;
        }
        pthread_mutex_unlock(&keyboard_lock);

        count = read(keyboard_fd, &value, 1);
        if (count == 1) {
            pthread_mutex_lock(&keyboard_lock);
            keyboard_data = value & 0x7f;
            keyboard_pending = 1;
            pthread_mutex_unlock(&keyboard_lock);

            /* The VTI keyboard interrupt is compatible with an 8080/Z80
             * RST 38H interrupt acknowledge byte. This also wakes software
             * which waits in HLT for a key rather than polling status.
             */
            int_data = 0xff;
            int_int = true;
            continue;
        }

        if (count < 0 && errno != EAGAIN && errno != EWOULDBLOCK && errno != EINTR)
            break;
        usleep(2000);
    }

    return NULL;
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

    /* Bit 7 selects character mode. A0H therefore represents an ASCII space
     * and gives a deterministic blank display at power-on.
     */
    memset(screen_map, 0xa0, TARGET_VTI_SIZE);
    msync(screen_map, TARGET_VTI_SIZE, MS_ASYNC);
    return 0;
}

static int init_keyboard(void)
{
    const char *configured = getenv("TARGET_VTI_KBD");

    keyboard_path = (configured != NULL && *configured != '\0')
        ? strdup(configured) : default_path("vti-kbd");
    if (keyboard_path == NULL)
        return -1;

    unlink(keyboard_path);
    if (mkfifo(keyboard_path, 0600) < 0)
        return -1;

    /* O_RDWR prevents an empty FIFO from continuously returning EOF when the
     * GTK front end is not currently connected.
     */
    keyboard_fd = open(keyboard_path, O_RDWR | O_NONBLOCK);
    if (keyboard_fd < 0)
        return -1;

    keyboard_running = 1;
    if (pthread_create(&keyboard_thread, NULL, keyboard_worker, NULL) != 0) {
        keyboard_running = 0;
        return -1;
    }
    keyboard_thread_started = 1;
    return 0;
}

void target_vti_init(void)
{
    vti_enabled = env_enabled("TARGET_VTI_ENABLE");
    if (!vti_enabled)
        return;

    if (init_screen() < 0 || init_keyboard() < 0) {
        fprintf(stderr, "target-vti: unable to initialize VTI shared display/keyboard\n");
        target_vti_exit();
        return;
    }

    map_vti_pages();
}

void target_vti_reset(void)
{
    if (!vti_enabled)
        return;

    map_vti_pages();
    pthread_mutex_lock(&keyboard_lock);
    keyboard_pending = 0;
    keyboard_data = 0;
    pthread_mutex_unlock(&keyboard_lock);
}

void target_vti_exit(void)
{
    if (keyboard_thread_started) {
        keyboard_running = 0;
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

    restore_vti_pages();

    if (screen_map != NULL) {
        msync(screen_map, TARGET_VTI_SIZE, MS_SYNC);
        munmap(screen_map, TARGET_VTI_SIZE);
        screen_map = NULL;
    }
    if (screen_fd >= 0) {
        close(screen_fd);
        screen_fd = -1;
    }

    pthread_mutex_lock(&keyboard_lock);
    keyboard_pending = 0;
    keyboard_data = 0;
    pthread_mutex_unlock(&keyboard_lock);
    vti_enabled = 0;
}

BYTE target_vti_keyboard_data_in(void)
{
    BYTE value = 0;

    if (!vti_enabled)
        return 0xff;

    pthread_mutex_lock(&keyboard_lock);
    if (keyboard_pending) {
        value = keyboard_data;
        keyboard_pending = 0;
        int_int = false;
    }
    pthread_mutex_unlock(&keyboard_lock);
    return value;
}

BYTE target_vti_keyboard_status_in(void)
{
    int pending;

    if (!vti_enabled)
        return 0xff;

    pthread_mutex_lock(&keyboard_lock);
    pending = keyboard_pending;
    pthread_mutex_unlock(&keyboard_lock);

    return pending ? VTI_PENDING_STATUS : VTI_IDLE_STATUS;
}
