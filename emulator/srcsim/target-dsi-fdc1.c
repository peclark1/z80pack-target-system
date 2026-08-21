/*
 * Software-visible emulation of the Digital Systems FDC-1 controller and
 * Altair-compatible host interface used by the target IMSAI's single-density
 * 8-inch disk subsystem.
 *
 * This deliberately models the documented FDC-1 programming interface, not
 * the later FDC-3 interface:
 *
 *   7Dh OUT  low byte of the 16-bit DMA address
 *   7Eh OUT  high byte of the 16-bit DMA address
 *   7Fh IN   controller status
 *   7Fh OUT  controller command
 *
 * Media are flat IBM-3740-style single-density images:
 *   77 tracks, one side, 26 sectors/track, 128 bytes/sector.
 *
 * Each controller transfer uses the authentic 131-byte DMA buffer layout:
 *   +0 track, +1 sector, +2 data address mark, +3..+130 sector data.
 */

#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>

#include "sim.h"
#include "simdefs.h"
#include "simmem.h"
#include "target-dsi-fdc1.h"

#define DSI_DRIVES              4
#define DSI_TRACKS              77
#define DSI_LAST_TRACK          76
#define DSI_SECTORS_PER_TRACK   26
#define DSI_SECTOR_SIZE         128
#define DSI_IMAGE_SIZE          ((uint64_t) DSI_TRACKS * \
                                 DSI_SECTORS_PER_TRACK * DSI_SECTOR_SIZE)
#define DSI_DATA_MARK           0xfb
#define PATH_SIZE               1024

/* FDC-1 command bits. */
#define CMD_INOP_RESET          0x01
#define CMD_STEP                0x02
#define CMD_DIRECTION_IN        0x04
#define CMD_SELECT_ENABLE       0x08
#define CMD_SELECT_MASK         0x30
#define CMD_SELECT_SHIFT        4
#define CMD_READ                0x40
#define CMD_WRITE               0x80

/* FDC-1 status bits. */
#define STAT_FILE_INOP          0x01
#define STAT_STEP_READY         0x02
#define STAT_TRACK_ZERO         0x04
#define STAT_IO_FINISH          0x08
#define STAT_TRACK_ERROR        0x10
#define STAT_ID_CRC_ERROR       0x20
#define STAT_DATA_CRC_ERROR     0x40
#define STAT_HEAD_UNLOADED      0x80

struct dsi_drive {
    FILE *fp;
    char path[PATH_SIZE];
    uint64_t size;
    int writable;
};

static struct dsi_drive drives[DSI_DRIVES];
static BYTE current_track[DSI_DRIVES];
static int selected_drive;
static BYTE dma_low;
static BYTE dma_high;
static BYTE previous_command;
static BYTE error_status;
static int io_finished;
static int head_unloaded;
static int file_inoperative;
static int trace_enabled;

static uint64_t file_size(FILE *fp)
{
    off_t here;
    off_t end;

    here = ftello(fp);
    if (here < 0)
        here = 0;
    if (fseeko(fp, 0, SEEK_END) != 0)
        return 0;
    end = ftello(fp);
    if (end < 0)
        end = 0;
    (void) fseeko(fp, here, SEEK_SET);
    return (uint64_t) end;
}

static void close_drive(struct dsi_drive *drive)
{
    if (drive->fp != NULL)
        fclose(drive->fp);
    memset(drive, 0, sizeof(*drive));
}

static void open_drive(int number)
{
    char env_name[32];
    const char *path;
    struct dsi_drive *drive = &drives[number];

    snprintf(env_name, sizeof(env_name), "TARGET_DSI%d", number);
    path = getenv(env_name);

    close_drive(drive);
    if (path == NULL || *path == '\0')
        return;

    snprintf(drive->path, sizeof(drive->path), "%s", path);
    drive->fp = fopen(path, "r+b");
    if (drive->fp != NULL) {
        drive->writable = 1;
    } else {
        drive->fp = fopen(path, "rb");
        drive->writable = 0;
    }

    if (drive->fp == NULL) {
        fprintf(stderr, "target-dsi: cannot open %s: %s\n",
                path, strerror(errno));
        drive->path[0] = '\0';
        return;
    }

    drive->size = file_size(drive->fp);
    if (drive->size != DSI_IMAGE_SIZE) {
        fprintf(stderr,
                "target-dsi: refusing DSI%d image %s: %llu bytes; "
                "expected %llu-byte 77x26x128 single-density image\n",
                number, drive->path,
                (unsigned long long) drive->size,
                (unsigned long long) DSI_IMAGE_SIZE);
        close_drive(drive);
        return;
    }

    if (trace_enabled) {
        fprintf(stderr,
                "target-dsi: DSI%d %s, %llu bytes%s\n",
                number, drive->path,
                (unsigned long long) drive->size,
                drive->writable ? "" : " (read-only)");
    }
}

static struct dsi_drive *current_drive(void)
{
    return &drives[selected_drive];
}

static int drive_ready(void)
{
    return selected_drive >= 0 && selected_drive < DSI_DRIVES &&
           current_drive()->fp != NULL;
}

static WORD dma_address(void)
{
    return (WORD) (((WORD) dma_high << 8) | dma_low);
}

static void trace_command(const char *name, BYTE track, BYTE sector, WORD dma)
{
    if (!trace_enabled)
        return;

    fprintf(stderr,
            "target-dsi: drive=%d %s track=%u sector=%u dma=%04X\n",
            selected_drive, name, track, sector, dma);
}

static void begin_io(void)
{
    io_finished = 0;
    error_status = 0;
    file_inoperative = 0;
}

static void fail_not_ready(void)
{
    file_inoperative = 1;
    head_unloaded = 1;
    io_finished = 0;
}

static void fail_track(void)
{
    error_status = STAT_TRACK_ERROR;
    io_finished = 1;
}

static void fail_sector(void)
{
    /*
     * The FDC-1 manual describes an impossible sector request as searching
     * until the head unloads, with IO FINISH remaining clear.  This status
     * lets authentic BIOS code escape its 88h (head-unload/IOF) wait loop
     * and then report the high-bit error condition.
     */
    head_unloaded = 1;
    io_finished = 0;
}

static uint64_t sector_offset(BYTE track, BYTE sector)
{
    return ((uint64_t) track * DSI_SECTORS_PER_TRACK +
            ((uint64_t) sector - 1u)) * DSI_SECTOR_SIZE;
}

static void read_sector(void)
{
    BYTE data[DSI_SECTOR_SIZE];
    WORD dma = dma_address();
    BYTE track = dma_read(dma);
    BYTE sector = dma_read((WORD) (dma + 1));
    uint64_t offset;
    size_t count;
    unsigned i;

    begin_io();
    trace_command("READ", track, sector, dma);

    if (!drive_ready()) {
        fail_not_ready();
        return;
    }

    head_unloaded = 0;

    if (track >= DSI_TRACKS || track != current_track[selected_drive]) {
        fail_track();
        return;
    }

    if (sector == 0 || sector > DSI_SECTORS_PER_TRACK) {
        fail_sector();
        return;
    }

    offset = sector_offset(track, sector);
    if (fseeko(current_drive()->fp, (off_t) offset, SEEK_SET) != 0) {
        fail_not_ready();
        return;
    }

    count = fread(data, 1, sizeof(data), current_drive()->fp);
    if (count != sizeof(data)) {
        fail_not_ready();
        return;
    }

    /* On reads the controller supplies the data address mark. */
    dma_write((WORD) (dma + 2), DSI_DATA_MARK);
    for (i = 0; i < DSI_SECTOR_SIZE; i++)
        dma_write((WORD) (dma + 3 + i), data[i]);

    io_finished = 1;
}

static void write_sector(void)
{
    BYTE data[DSI_SECTOR_SIZE];
    WORD dma = dma_address();
    BYTE track = dma_read(dma);
    BYTE sector = dma_read((WORD) (dma + 1));
    BYTE mark = dma_read((WORD) (dma + 2));
    uint64_t offset;
    size_t count;
    unsigned i;

    begin_io();
    trace_command("WRITE", track, sector, dma);

    if (!drive_ready() || !current_drive()->writable) {
        fail_not_ready();
        return;
    }

    head_unloaded = 0;

    if (track >= DSI_TRACKS || track != current_track[selected_drive]) {
        fail_track();
        return;
    }

    if (sector == 0 || sector > DSI_SECTORS_PER_TRACK) {
        fail_sector();
        return;
    }

    if (trace_enabled && mark != DSI_DATA_MARK) {
        fprintf(stderr,
                "target-dsi: write address mark %02X (usual SD mark is FB)\n",
                mark);
    }

    for (i = 0; i < DSI_SECTOR_SIZE; i++)
        data[i] = dma_read((WORD) (dma + 3 + i));

    offset = sector_offset(track, sector);
    if (fseeko(current_drive()->fp, (off_t) offset, SEEK_SET) != 0) {
        fail_not_ready();
        return;
    }

    count = fwrite(data, 1, sizeof(data), current_drive()->fp);
    if (count != sizeof(data) || fflush(current_drive()->fp) != 0) {
        fail_not_ready();
        return;
    }

    io_finished = 1;
}

static void step_selected_drive(BYTE command)
{
    BYTE *track;

    if (selected_drive < 0 || selected_drive >= DSI_DRIVES)
        return;

    track = &current_track[selected_drive];

    if (command & CMD_DIRECTION_IN) {
        if (*track < DSI_LAST_TRACK)
            (*track)++;
    } else {
        if (*track > 0)
            (*track)--;
    }

    if (trace_enabled) {
        fprintf(stderr,
                "target-dsi: drive=%d step %s -> track=%u\n",
                selected_drive,
                (command & CMD_DIRECTION_IN) ? "IN" : "OUT",
                *track);
    }
}

BYTE target_dsi_fdc1_status_in(void)
{
    BYTE status = error_status;

    if (file_inoperative)
        status |= STAT_FILE_INOP;

    /* Stepping is instantaneous in the emulator, so it is always ready. */
    status |= STAT_STEP_READY;

    if (selected_drive >= 0 && selected_drive < DSI_DRIVES &&
        current_track[selected_drive] == 0)
        status |= STAT_TRACK_ZERO;

    if (io_finished)
        status |= STAT_IO_FINISH;

    if (head_unloaded || !drive_ready())
        status |= STAT_HEAD_UNLOADED;

    return status;
}

void target_dsi_fdc1_dma_low_out(BYTE data)
{
    dma_low = data;
    if (trace_enabled)
        fprintf(stderr, "target-dsi: DMA low=%02X -> %04X\n",
                data, dma_address());
}

void target_dsi_fdc1_dma_high_out(BYTE data)
{
    dma_high = data;
    if (trace_enabled)
        fprintf(stderr, "target-dsi: DMA high=%02X -> %04X\n",
                data, dma_address());
}

void target_dsi_fdc1_command_out(BYTE data)
{
    int drive;

    if (data & CMD_INOP_RESET) {
        file_inoperative = 0;
        error_status = 0;
    }

    if (data & CMD_SELECT_ENABLE) {
        drive = (data & CMD_SELECT_MASK) >> CMD_SELECT_SHIFT;
        if (drive != selected_drive)
            head_unloaded = 1;
        selected_drive = drive;
        if (trace_enabled)
            fprintf(stderr, "target-dsi: selected drive %d\n", selected_drive);
    }

    /* CBIOS14 pulses STEP low -> high -> low; move on the rising edge. */
    if ((data & CMD_STEP) && !(previous_command & CMD_STEP)) {
        io_finished = 0;
        step_selected_drive(data);
    }

    if (data & CMD_READ)
        read_sector();
    else if (data & CMD_WRITE)
        write_sector();

    previous_command = data;
}

void target_dsi_fdc1_reset(void)
{
    selected_drive = 0;
    dma_low = 0;
    dma_high = 0;
    previous_command = 0;
    error_status = 0;
    io_finished = 0;
    head_unloaded = 1;
    file_inoperative = 0;
    memset(current_track, 0, sizeof(current_track));
}

void target_dsi_fdc1_init(void)
{
    const char *trace = getenv("TARGET_DSI_TRACE");
    int i;

    trace_enabled = trace != NULL && *trace != '\0' && strcmp(trace, "0") != 0;

    for (i = 0; i < DSI_DRIVES; i++)
        open_drive(i);

    target_dsi_fdc1_reset();
}

void target_dsi_fdc1_exit(void)
{
    int i;

    for (i = 0; i < DSI_DRIVES; i++)
        close_drive(&drives[i]);
}
