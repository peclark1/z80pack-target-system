/*
 * Emulator-only cold-start helper for the dedicated FDC+/VTI CP/M profile.
 *
 * The physical target has no ROM when the FDC+ RAM is enabled through FBFFH
 * and the Polymorphic VTI occupies FC00H-FFFFH. During software development
 * the emulator therefore performs the one job a small bootstrap PROM/front
 * panel loader would perform: copy the 51 CP/M 2.2 system sectors from FDC+
 * drive 0 into their relocated memory addresses, then z80pack begins at the
 * BIOS cold-boot entry selected by fdcplus-vti.conf.
 *
 * This helper is intentionally NOT a replacement for the emulated FDC+. Once
 * CP/M starts, its BIOS talks to the normal Drive Type 8 emulator at 08H/09H.
 * The final physical cold-start mechanism remains a separate integration task.
 */

#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>

#include "sim.h"
#include "simglb.h"
#include "simmem.h"
#include "target-fdcplus-bootstrap.h"

#define TRACKS              77u
#define SECTORS_PER_TRACK   26u
#define SECTOR_SIZE         128u
#define IMAGE_SIZE          (TRACKS * SECTORS_PER_TRACK * SECTOR_SIZE)
#define SYSTEM_SECTORS      51u
#define SYSTEM_BYTES        (SYSTEM_SECTORS * SECTOR_SIZE)
#define DEFAULT_LOAD_BASE   0xe200u
#define VTI_BASE_LIMIT      0xfc00u

static int env_enabled(const char *name)
{
    const char *value = getenv(name);

    if (value == NULL || *value == '\0')
        return 0;
    return strcmp(value, "0") != 0 && strcasecmp(value, "false") != 0 &&
           strcasecmp(value, "no") != 0;
}

static unsigned parse_load_base(void)
{
    const char *text = getenv("TARGET_FDCPLUS_CPM_LOAD");
    char *end = NULL;
    unsigned long value;

    if (text == NULL || *text == '\0')
        return DEFAULT_LOAD_BASE;

    value = strtoul(text, &end, 0);
    if (end == text || *end != '\0' || value > 0xffffu) {
        fprintf(stderr,
                "target-fdcplus-bootstrap: invalid load address '%s'; using %04XH\n",
                text, DEFAULT_LOAD_BASE);
        return DEFAULT_LOAD_BASE;
    }
    return (unsigned) value;
}

static long sector_offset(unsigned track, unsigned sector)
{
    return (long) ((track * SECTORS_PER_TRACK + (sector - 1u)) * SECTOR_SIZE);
}

static int copy_sector(FILE *fp, unsigned track, unsigned sector,
                       unsigned *destination)
{
    unsigned char buffer[SECTOR_SIZE];
    size_t count;
    unsigned i;

    if (fseek(fp, sector_offset(track, sector), SEEK_SET) != 0)
        return -1;
    count = fread(buffer, 1, sizeof(buffer), fp);
    if (count != sizeof(buffer))
        return -1;

    for (i = 0; i < SECTOR_SIZE; i++)
        putmem((WORD) ((*destination)++), (BYTE) buffer[i]);
    return 0;
}

void target_fdcplus_bootstrap_init(void)
{
    const char *path;
    FILE *fp;
    long size;
    unsigned load_base;
    unsigned destination;
    unsigned sector;
    unsigned copied = 0;

    if (!env_enabled("TARGET_FDCPLUS_CPM_BOOTSTRAP"))
        return;

    path = getenv("TARGET_FDCPLUS0");
    if (path == NULL || *path == '\0') {
        fprintf(stderr,
                "target-fdcplus-bootstrap: TARGET_FDCPLUS0 is required\n");
        return;
    }

    load_base = parse_load_base();
    destination = load_base;
    if (destination + SYSTEM_BYTES > VTI_BASE_LIMIT) {
        fprintf(stderr,
                "target-fdcplus-bootstrap: system image %04XH-%04XH would overlap VTI at FC00H\n",
                destination, destination + SYSTEM_BYTES - 1u);
        return;
    }

    fp = fopen(path, "rb");
    if (fp == NULL) {
        fprintf(stderr, "target-fdcplus-bootstrap: cannot open %s: %s\n",
                path, strerror(errno));
        return;
    }

    if (fseek(fp, 0, SEEK_END) != 0) {
        fclose(fp);
        return;
    }
    size = ftell(fp);
    if (size != (long) IMAGE_SIZE) {
        fprintf(stderr,
                "target-fdcplus-bootstrap: refusing %s: %ld bytes; expected %u-byte IBM-3740 image\n",
                path, size, IMAGE_SIZE);
        fclose(fp);
        return;
    }

    /* Mike Douglas's physical loader reads these sectors with an odd/even
     * interleave for rotational performance, but places them in ordinary
     * logical order in memory. A host-side direct loader therefore copies
     * track 0 sectors 2..26 followed by track 1 sectors 1..26. Sector 1 of
     * track 0 is the bootstrap sector and is not part of the 51-sector CP/M
     * image.
     */
    for (sector = 2; sector <= 26; sector++) {
        if (copy_sector(fp, 0, sector, &destination) < 0)
            goto read_error;
        copied++;
    }
    for (sector = 1; sector <= 26; sector++) {
        if (copy_sector(fp, 1, sector, &destination) < 0)
            goto read_error;
        copied++;
    }

    fclose(fp);
    if (copied != SYSTEM_SECTORS) {
        fprintf(stderr,
                "target-fdcplus-bootstrap: internal sector-count error (%u)\n",
                copied);
        return;
    }

    fprintf(stderr,
            "target-fdcplus-bootstrap: loaded %u CP/M system sectors at %04XH-%04XH from drive 0\n",
            copied, load_base, destination - 1u);
    return;

read_error:
    fprintf(stderr,
            "target-fdcplus-bootstrap: read failed at system sector %u: %s\n",
            copied + 1u, ferror(fp) ? strerror(errno) : "short read");
    fclose(fp);
}
