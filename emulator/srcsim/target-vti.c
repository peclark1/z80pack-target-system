/*
 * Polymorphic Systems Video Terminal Interface (VTI) overlay.
 *
 * Surviving software from the restored IMSAI workstation (VID.HEX) directly
 * addresses the VTI display RAM at F800H-FBFFH. That software is stronger
 * evidence for this machine than the generic non-Poly-88 8800H convention.
 *
 * The restored workstation did not have a keyboard connected to the VTI. Its
 * normal operator input/output remained on the console/terminal while selected
 * output could be redirected to the VTI. Accordingly this model exposes only
 * the 1 KB memory-mapped display.
 *
 * TARGET_VTI_ENABLE=1 enables the device. TARGET_VTI_SCREEN names a 1024-byte
 * shared file used by the GTK front end.
 */

#include <fcntl.h>
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

#define VTI_FIRST_PAGE (TARGET_VTI_BASE >> 8)
#define VTI_PAGE_COUNT (TARGET_VTI_SIZE >> 8)

static int vti_enabled;
static int screen_fd = -1;
static BYTE *screen_map;
static BYTE *saved_rdrvec[VTI_PAGE_COUNT];
static BYTE *saved_wrtvec[VTI_PAGE_COUNT];
static int vectors_saved;

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

    /* Bit 7 selects character mode. A0H is therefore an ASCII space. VID.HEX
     * later clears the display with 3FH semigraphics blanks when installed.
     */
    memset(screen_map, 0xa0, TARGET_VTI_SIZE);
    msync(screen_map, TARGET_VTI_SIZE, MS_ASYNC);
    return 0;
}

void target_vti_init(void)
{
    vti_enabled = env_enabled("TARGET_VTI_ENABLE");
    if (!vti_enabled)
        return;

    if (init_screen() < 0) {
        fprintf(stderr, "target-vti: unable to initialize VTI shared display\n");
        target_vti_exit();
        return;
    }

    map_vti_pages();
}

void target_vti_reset(void)
{
    if (vti_enabled)
        map_vti_pages();
}

void target_vti_exit(void)
{
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

    vti_enabled = 0;
}
