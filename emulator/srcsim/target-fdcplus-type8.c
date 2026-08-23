/*
 * Software-visible emulation of the Altair FDC+ in Drive Type 8 mode.
 *
 * Drive Type 8 makes attached Shugart-compatible drives look like an
 * iCOM/Pertec FD3712 controller and its S-100 interface card, relocated to
 * the FDC+ default I/O base. The optimized FDC+3712 boot PROM uses:
 *
 *   08h IN   controller status / read FIFO data
 *   08h OUT  FD3712 command
 *   09h OUT  controller data latch
 *
 * Media are flat IBM-3740 images:
 *   77 tracks, one side, 26 sectors/track, 128 bytes/sector (256256 bytes).
 *
 * The controller is intentionally instantaneous at the emulator level. The
 * guest still executes the authentic command/status protocol, but BUSY is
 * clear by the time software polls status. This keeps the implementation
 * deterministic while preserving the interface exercised by the CP/M BIOS.
 */

#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>

#include "sim.h"
#include "target-fdcplus-type8.h"

#define FDCPLUS_DRIVES              4
#define FDCPLUS_TRACKS              77
#define FDCPLUS_LAST_TRACK          76
#define FDCPLUS_SECTORS_PER_TRACK   26
#define FDCPLUS_SECTOR_SIZE         128
#define FDCPLUS_IMAGE_SIZE          ((uint64_t) FDCPLUS_TRACKS * \
                                     FDCPLUS_SECTORS_PER_TRACK * \
                                     FDCPLUS_SECTOR_SIZE)
#define PATH_SIZE                   1024

/* FD3712 commands used by the FDC+3712 ROM/BIOS. */
#define CMD_STATUS                  0x00
#define CMD_READ                    0x03
#define CMD_WRITE                   0x05
#define CMD_READ_CRC                0x07
#define CMD_SEEK                    0x09
#define CMD_CLEAR_ERRORS            0x0b
#define CMD_RESTORE                 0x0d
#define CMD_SET_TRACK               0x11
#define CMD_LOAD_CONFIG             0x15
#define CMD_DRIVE_SECTOR            0x21
#define CMD_WRITE_BUFFER            0x31
#define CMD_READ_BUFFER             0x40
#define CMD_SHIFT_BUFFER            0x41
#define CMD_RESET                   0x81

/* FD3712 controller status bits. BUSY is always clear after a command here. */
#define STAT_BUSY                   0x01
#define STAT_SEEK_ERROR             0x02
#define STAT_CRC_ERROR              0x08
#define STAT_WRITE_PROTECT          0x10
#define STAT_NOT_READY              0x20

struct fdcplus_drive {
    FILE *fp;
    char path[PATH_SIZE];
    uint64_t size;
    int writable;
};

static struct fdcplus_drive drives[FDCPLUS_DRIVES];
static BYTE current_track[FDCPLUS_DRIVES];
static BYTE selected_drive;
static BYTE selected_sector;
static BYTE requested_track;
static BYTE data_latch;
static BYTE input_latch;
static BYTE config_latch;
static BYTE error_status;
static BYTE read_buffer[FDCPLUS_SECTOR_SIZE];
static unsigned read_index;
static BYTE write_buffer[FDCPLUS_SECTOR_SIZE];
static unsigned write_index;
static unsigned write_count;
static int trace_enabled;
static int write_enabled;

static int env_enabled(const char *name)
{
    const char *value = getenv(name);

    return value != NULL && *value != '\0' && strcmp(value, "0") != 0;
}

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

static void close_drive(struct fdcplus_drive *drive)
{
    if (drive->fp != NULL)
        fclose(drive->fp);
    memset(drive, 0, sizeof(*drive));
}

static void open_drive(int number)
{
    char env_name[32];
    const char *path;
    struct fdcplus_drive *drive = &drives[number];

    snprintf(env_name, sizeof(env_name), "TARGET_FDCPLUS%d", number);
    path = getenv(env_name);

    close_drive(drive);
    if (path == NULL || *path == '\0')
        return;

    snprintf(drive->path, sizeof(drive->path), "%s", path);

    /* Preserve archival media by default. Writes require an explicit opt-in. */
    if (write_enabled) {
        drive->fp = fopen(path, "r+b");
        if (drive->fp != NULL)
            drive->writable = 1;
    }

    if (drive->fp == NULL) {
        drive->fp = fopen(path, "rb");
        drive->writable = 0;
    }

    if (drive->fp == NULL) {
        fprintf(stderr, "target-fdcplus8: cannot open %s: %s\n",
                path, strerror(errno));
        drive->path[0] = '\0';
        return;
    }

    drive->size = file_size(drive->fp);
    if (drive->size != FDCPLUS_IMAGE_SIZE) {
        fprintf(stderr,
                "target-fdcplus8: refusing drive %d image %s: %llu bytes; "
                "expected %llu-byte 77x26x128 IBM-3740 image\n",
                number, drive->path,
                (unsigned long long) drive->size,
                (unsigned long long) FDCPLUS_IMAGE_SIZE);
        close_drive(drive);
        return;
    }

    if (trace_enabled) {
        fprintf(stderr,
                "target-fdcplus8: drive %d %s, %llu bytes%s\n",
                number, drive->path,
                (unsigned long long) drive->size,
                drive->writable ? " (writable)" : " (read-only)");
    }
}

static struct fdcplus_drive *current_drive(void)
{
    return &drives[selected_drive & 0x03];
}

static int drive_ready(void)
{
    return selected_drive < FDCPLUS_DRIVES && current_drive()->fp != NULL;
}

static BYTE status_value(void)
{
    BYTE status = error_status & (BYTE) ~STAT_BUSY;

    if (!drive_ready())
        status |= STAT_NOT_READY;
    else if (!current_drive()->writable)
        status |= STAT_WRITE_PROTECT;

    return status;
}

static uint64_t sector_offset(BYTE track, BYTE sector)
{
    return ((uint64_t) track * FDCPLUS_SECTORS_PER_TRACK +
            ((uint64_t) sector - 1u)) * FDCPLUS_SECTOR_SIZE;
}

static void trace_operation(const char *name)
{
    if (!trace_enabled)
        return;

    fprintf(stderr,
            "target-fdcplus8: drive=%u %s track=%u sector=%u status=%02X\n",
            (unsigned) selected_drive, name,
            (unsigned) current_track[selected_drive & 0x03],
            (unsigned) selected_sector,
            (unsigned) status_value());
}

static int position_valid(void)
{
    if (!drive_ready()) {
        error_status |= STAT_NOT_READY;
        return 0;
    }

    if (current_track[selected_drive] >= FDCPLUS_TRACKS) {
        error_status |= STAT_SEEK_ERROR | STAT_CRC_ERROR;
        return 0;
    }

    if (selected_sector == 0 ||
        selected_sector > FDCPLUS_SECTORS_PER_TRACK) {
        error_status |= STAT_CRC_ERROR;
        return 0;
    }

    return 1;
}

static void read_sector(void)
{
    struct fdcplus_drive *drive;
    uint64_t offset;
    size_t count;

    if (!position_valid()) {
        trace_operation("READ failed");
        return;
    }

    drive = current_drive();
    offset = sector_offset(current_track[selected_drive], selected_sector);
    if (fseeko(drive->fp, (off_t) offset, SEEK_SET) != 0) {
        error_status |= STAT_NOT_READY;
        trace_operation("READ seek failed");
        return;
    }

    count = fread(read_buffer, 1, sizeof(read_buffer), drive->fp);
    if (count != sizeof(read_buffer)) {
        clearerr(drive->fp);
        error_status |= STAT_CRC_ERROR;
        trace_operation("READ short");
        return;
    }

    read_index = 0;
    trace_operation("READ");
}

static void write_sector(void)
{
    struct fdcplus_drive *drive;
    uint64_t offset;
    size_t count;

    if (!position_valid()) {
        trace_operation("WRITE failed");
        return;
    }

    drive = current_drive();
    if (!drive->writable) {
        /*
         * The controller has a distinct write-protect bit. Also return the
         * operation-failure bit checked by the historical FDC+3712 CP/M BIOS
         * so a protected emulator image cannot be silently reported written.
         */
        error_status |= STAT_WRITE_PROTECT | STAT_NOT_READY;
        trace_operation("WRITE protected");
        return;
    }

    if (write_count < FDCPLUS_SECTOR_SIZE) {
        error_status |= STAT_CRC_ERROR;
        trace_operation("WRITE short buffer");
        return;
    }

    offset = sector_offset(current_track[selected_drive], selected_sector);
    if (fseeko(drive->fp, (off_t) offset, SEEK_SET) != 0) {
        error_status |= STAT_NOT_READY;
        trace_operation("WRITE seek failed");
        return;
    }

    count = fwrite(write_buffer, 1, sizeof(write_buffer), drive->fp);
    if (count != sizeof(write_buffer) || fflush(drive->fp) != 0) {
        error_status |= STAT_NOT_READY;
        trace_operation("WRITE failed");
        return;
    }

    /* Retain the buffer for a possible WRITE retry, but restart the load
     * pointer when software begins filling the next sector buffer.
     */
    write_index = 0;
    trace_operation("WRITE");
}

static void check_crc(void)
{
    BYTE probe[FDCPLUS_SECTOR_SIZE];
    struct fdcplus_drive *drive;
    uint64_t offset;
    size_t count;

    if (!position_valid()) {
        trace_operation("RDCRC failed");
        return;
    }

    drive = current_drive();
    offset = sector_offset(current_track[selected_drive], selected_sector);
    if (fseeko(drive->fp, (off_t) offset, SEEK_SET) != 0) {
        error_status |= STAT_NOT_READY;
        trace_operation("RDCRC seek failed");
        return;
    }

    count = fread(probe, 1, sizeof(probe), drive->fp);
    if (count != sizeof(probe)) {
        clearerr(drive->fp);
        error_status |= STAT_CRC_ERROR;
    }

    trace_operation("RDCRC");
}

static void seek_track(void)
{
    if (!drive_ready()) {
        error_status |= STAT_NOT_READY;
        trace_operation("SEEK not ready");
        return;
    }

    if (requested_track >= FDCPLUS_TRACKS) {
        error_status |= STAT_SEEK_ERROR | STAT_CRC_ERROR;
        trace_operation("SEEK invalid");
        return;
    }

    current_track[selected_drive] = requested_track;
    trace_operation("SEEK");
}

static void restore_track_zero(void)
{
    if (!drive_ready())
        error_status |= STAT_NOT_READY;

    current_track[selected_drive & 0x03] = 0;
    trace_operation("RESTORE");
}

static void soft_reset(void)
{
    selected_drive = 0;
    selected_sector = 1;
    requested_track = 0;
    data_latch = 0;
    input_latch = 0;
    config_latch = 0;
    error_status = 0;
    read_index = 0;
    write_index = 0;
    write_count = 0;
    memset(read_buffer, 0, sizeof(read_buffer));
    memset(write_buffer, 0, sizeof(write_buffer));
}

BYTE target_fdcplus_type8_status_data_in(void)
{
    return input_latch;
}

void target_fdcplus_type8_data_out(BYTE data)
{
    data_latch = data;
}

void target_fdcplus_type8_command_out(BYTE command)
{
    switch (command) {
    case CMD_STATUS:
        input_latch = status_value();
        break;

    case CMD_READ:
        read_sector();
        break;

    case CMD_WRITE:
        write_sector();
        break;

    case CMD_READ_CRC:
        check_crc();
        break;

    case CMD_SEEK:
        seek_track();
        break;

    case CMD_CLEAR_ERRORS:
        error_status = 0;
        if (trace_enabled)
            fprintf(stderr, "target-fdcplus8: CLEAR ERRORS\n");
        break;

    case CMD_RESTORE:
        restore_track_zero();
        break;

    case CMD_SET_TRACK:
        requested_track = data_latch;
        if (trace_enabled)
            fprintf(stderr, "target-fdcplus8: SET TRACK %u\n",
                    (unsigned) requested_track);
        break;

    case CMD_LOAD_CONFIG:
        config_latch = data_latch;
        if (trace_enabled && config_latch != 0)
            fprintf(stderr, "target-fdcplus8: LOAD CONFIG %02X (accepted)\n",
                    (unsigned) config_latch);
        break;

    case CMD_DRIVE_SECTOR:
        selected_drive = (BYTE) ((data_latch >> 6) & 0x03);
        selected_sector = (BYTE) (data_latch & 0x1f);
        if (trace_enabled)
            fprintf(stderr,
                    "target-fdcplus8: DRIVE/SECTOR drive=%u sector=%u\n",
                    (unsigned) selected_drive,
                    (unsigned) selected_sector);
        break;

    case CMD_WRITE_BUFFER:
        if (write_index == 0)
            write_count = 0;
        if (write_index < FDCPLUS_SECTOR_SIZE) {
            write_buffer[write_index++] = data_latch;
            write_count = write_index;
        } else {
            error_status |= STAT_CRC_ERROR;
        }
        break;

    case CMD_READ_BUFFER:
        if (read_index < FDCPLUS_SECTOR_SIZE)
            input_latch = read_buffer[read_index];
        else
            input_latch = 0xff;
        break;

    case CMD_SHIFT_BUFFER:
        if (read_index < FDCPLUS_SECTOR_SIZE)
            read_index++;
        if (read_index < FDCPLUS_SECTOR_SIZE)
            input_latch = read_buffer[read_index];
        else
            input_latch = 0xff;
        break;

    case CMD_RESET:
        soft_reset();
        if (trace_enabled)
            fprintf(stderr, "target-fdcplus8: controller RESET\n");
        break;

    default:
        if (trace_enabled)
            fprintf(stderr,
                    "target-fdcplus8: unsupported command %02X "
                    "(data=%02X drive=%u track=%u sector=%u)\n",
                    (unsigned) command, (unsigned) data_latch,
                    (unsigned) selected_drive,
                    (unsigned) current_track[selected_drive & 0x03],
                    (unsigned) selected_sector);
        break;
    }
}

BYTE target_fdcplus_type8_port0a_in(void)
{
    if (trace_enabled)
        fprintf(stderr,
                "target-fdcplus8: IN 0A -> FF (Type 8 data/status is IN 08)\n");
    return 0xff;
}

void target_fdcplus_type8_port0a_out(BYTE data)
{
    if (trace_enabled)
        fprintf(stderr,
                "target-fdcplus8: OUT 0A,%02X ignored "
                "(Type 8 data latch is OUT 09)\n",
                (unsigned) data);
}

BYTE target_fdcplus_type8_port0b_in(void)
{
    if (trace_enabled)
        fprintf(stderr, "target-fdcplus8: IN 0B -> FF (reserved)\n");
    return 0xff;
}

void target_fdcplus_type8_port0b_out(BYTE data)
{
    if (trace_enabled)
        fprintf(stderr,
                "target-fdcplus8: OUT 0B,%02X ignored (reserved)\n",
                (unsigned) data);
}

void target_fdcplus_type8_reset(void)
{
    memset(current_track, 0, sizeof(current_track));
    soft_reset();
}

void target_fdcplus_type8_init(void)
{
    int i;

    trace_enabled = env_enabled("TARGET_FDCPLUS_TRACE");
    write_enabled = env_enabled("TARGET_FDCPLUS_WRITE");

    for (i = 0; i < FDCPLUS_DRIVES; i++)
        open_drive(i);

    target_fdcplus_type8_reset();
}

void target_fdcplus_type8_exit(void)
{
    int i;

    for (i = 0; i < FDCPLUS_DRIVES; i++)
        close_drive(&drives[i]);
}
