/*
 * Software-visible emulation of the S100Computers Dual IDE/CF V3 board.
 *
 * The real board presents an ATA/CF device through an 8255 PPI.  The target
 * monitor selects an ATA register with the low nibble of PPI port C and uses
 * bit 6 as /RD, bit 5 as /WR, and bit 7 as RESET.  PPI ports A/B carry the
 * low/high bytes of the 16-bit ATA data bus.
 *
 * This model deliberately implements the board at that software boundary.  It
 * does not attempt to emulate individual TTL devices or electrical timing.
 */

#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>

#include "sim.h"
#include "simdefs.h"
#include "target-ide.h"

#define IDE_RESET_BIT       0x80
#define IDE_RD_BIT          0x40
#define IDE_WR_BIT          0x20
#define IDE_SELECT_MASK     0x0f
#define IDE_SELECT_BASE     0x08

#define ATA_REG_DATA        0
#define ATA_REG_ERROR       1
#define ATA_REG_FEATURES    1
#define ATA_REG_COUNT       2
#define ATA_REG_SECTOR      3
#define ATA_REG_CYL_LO      4
#define ATA_REG_CYL_HI      5
#define ATA_REG_SDH         6
#define ATA_REG_STATUS      7
#define ATA_REG_COMMAND     7

#define ATA_STATUS_ERR      0x01
#define ATA_STATUS_DRQ      0x08
#define ATA_STATUS_DRDY     0x40
#define ATA_STATUS_BSY      0x80

#define ATA_ERROR_ABRT      0x04
#define ATA_ERROR_IDNF      0x10

#define ATA_CMD_READ        0x20
#define ATA_CMD_WRITE       0x30
#define ATA_CMD_IDENTIFY    0xec
#define ATA_CMD_FLUSH       0xe7
#define ATA_CMD_SET_FEATURE 0xef

#define SECTOR_SIZE         512u
#define DRIVE_COUNT         2
#define PATH_SIZE           1024

struct target_drive {
    FILE *fp;
    char path[PATH_SIZE];
    uint64_t size;
    int writable;
};

enum transfer_kind {
    XFER_NONE,
    XFER_READ,
    XFER_WRITE,
    XFER_IDENTIFY
};

static struct target_drive drives[DRIVE_COUNT];
static int selected_drive;
static int trace_enabled;

/* 8255-visible latches */
static BYTE ppi_a;
static BYTE ppi_b;
static BYTE ppi_c;
static BYTE ppi_ctrl;

/* ATA task-file registers */
static BYTE ata_error;
static BYTE ata_features;
static BYTE ata_count;
static BYTE ata_sector;
static BYTE ata_cyl_lo;
static BYTE ata_cyl_hi;
static BYTE ata_sdh;
static BYTE ata_status;

static enum transfer_kind transfer;
static uint32_t sectors_remaining;
static unsigned sector_bytes_remaining;
static BYTE identify_data[SECTOR_SIZE];
static unsigned identify_pos;

static struct target_drive *current_drive(void)
{
    return &drives[selected_drive & 1];
}

static int drive_ready(void)
{
    return current_drive()->fp != NULL;
}

static void trace(const char *message)
{
    if (trace_enabled)
        fprintf(stderr, "target-ide: %s\n", message);
}

static void trace_command(BYTE command, uint32_t lba, uint32_t sectors)
{
    if (trace_enabled) {
        fprintf(stderr,
                "target-ide: drive=%d command=%02X lba=%" PRIu32
                " sectors=%" PRIu32 "\n",
                selected_drive, command, lba, sectors);
    }
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

static void close_drive(struct target_drive *drive)
{
    if (drive->fp != NULL)
        fclose(drive->fp);
    memset(drive, 0, sizeof(*drive));
}

static void open_drive(int number, const char *env_name)
{
    const char *path = getenv(env_name);
    struct target_drive *drive = &drives[number];

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
        if (trace_enabled)
            fprintf(stderr, "target-ide: cannot open %s: %s\n",
                    path, strerror(errno));
        drive->path[0] = '\0';
        return;
    }

    drive->size = file_size(drive->fp);
    if (trace_enabled) {
        fprintf(stderr,
                "target-ide: CF%d %s, %" PRIu64 " bytes%s\n",
                number, drive->path, drive->size,
                drive->writable ? "" : " (read-only)");
    }
}

static void ata_set_ready(void)
{
    ata_status = drive_ready() ? ATA_STATUS_DRDY : 0;
}

static void ata_fail(BYTE error)
{
    ata_error = error;
    ata_status = drive_ready() ? (ATA_STATUS_DRDY | ATA_STATUS_ERR)
                               : ATA_STATUS_ERR;
    transfer = XFER_NONE;
    sectors_remaining = 0;
    sector_bytes_remaining = 0;
}

static uint32_t taskfile_lba(void)
{
    return ((uint32_t) (ata_sdh & 0x0f) << 24) |
           ((uint32_t) ata_cyl_hi << 16) |
           ((uint32_t) ata_cyl_lo << 8) |
           (uint32_t) ata_sector;
}

static void set_taskfile_lba(uint32_t lba)
{
    ata_sector = (BYTE) lba;
    ata_cyl_lo = (BYTE) (lba >> 8);
    ata_cyl_hi = (BYTE) (lba >> 16);
    ata_sdh = (BYTE) ((ata_sdh & 0xf0) | ((lba >> 24) & 0x0f));
}

static uint32_t requested_sector_count(void)
{
    return ata_count == 0 ? 256u : (uint32_t) ata_count;
}

static void finish_sector(void)
{
    uint32_t lba;

    if (sectors_remaining == 0)
        return;

    sectors_remaining--;
    lba = taskfile_lba() + 1;
    set_taskfile_lba(lba);
    ata_count = (BYTE) sectors_remaining;

    if (sectors_remaining == 0) {
        if (transfer == XFER_WRITE && current_drive()->fp != NULL)
            fflush(current_drive()->fp);
        transfer = XFER_NONE;
        sector_bytes_remaining = 0;
        ata_status = ATA_STATUS_DRDY;
    } else {
        sector_bytes_remaining = SECTOR_SIZE;
        ata_status = ATA_STATUS_DRDY | ATA_STATUS_DRQ;
    }
}

static int seek_transfer(uint32_t lba, uint32_t sectors, int writing)
{
    struct target_drive *drive = current_drive();
    uint64_t offset = (uint64_t) lba * SECTOR_SIZE;
    uint64_t length = (uint64_t) sectors * SECTOR_SIZE;

    if (drive->fp == NULL)
        return 0;
    if (writing && !drive->writable)
        return 0;
    if (offset > drive->size || length > drive->size - offset)
        return 0;
    if (fseeko(drive->fp, (off_t) offset, SEEK_SET) != 0)
        return 0;
    return 1;
}

static void start_file_transfer(enum transfer_kind kind, BYTE command)
{
    uint32_t lba = taskfile_lba();
    uint32_t sectors = requested_sector_count();
    int writing = kind == XFER_WRITE;

    trace_command(command, lba, sectors);

    if (!seek_transfer(lba, sectors, writing)) {
        ata_fail(drive_ready() ? ATA_ERROR_IDNF : ATA_ERROR_ABRT);
        return;
    }

    transfer = kind;
    sectors_remaining = sectors;
    sector_bytes_remaining = SECTOR_SIZE;
    ata_error = 0;
    ata_status = ATA_STATUS_DRDY | ATA_STATUS_DRQ;
}

static void identify_put_word(unsigned word, uint16_t value)
{
    unsigned offset = word * 2;
    identify_data[offset] = (BYTE) value;
    identify_data[offset + 1] = (BYTE) (value >> 8);
}

static void identify_put_string(unsigned first_word, unsigned words,
                                const char *text)
{
    unsigned i;
    unsigned length = words * 2;
    char temp[64];

    if (length > sizeof(temp))
        length = sizeof(temp);
    memset(temp, ' ', length);
    if (text != NULL) {
        size_t n = strlen(text);
        if (n > length)
            n = length;
        memcpy(temp, text, n);
    }

    for (i = 0; i < length; i += 2) {
        unsigned offset = first_word * 2 + i;
        identify_data[offset] = (BYTE) temp[i + 1];
        identify_data[offset + 1] = (BYTE) temp[i];
    }
}

static void start_identify(void)
{
    struct target_drive *drive = current_drive();
    uint64_t sectors64;
    uint32_t sectors;

    if (drive->fp == NULL) {
        ata_fail(ATA_ERROR_ABRT);
        return;
    }

    memset(identify_data, 0, sizeof(identify_data));
    sectors64 = drive->size / SECTOR_SIZE;
    sectors = sectors64 > 0xffffffffu ? 0xffffffffu : (uint32_t) sectors64;

    identify_put_word(0, 0x0040);       /* fixed disk */
    identify_put_word(47, 0x8001);      /* one-sector multiple maximum */
    identify_put_word(49, 0x0200);      /* LBA supported */
    identify_put_word(53, 0x0001);
    identify_put_word(60, (uint16_t) sectors);
    identify_put_word(61, (uint16_t) (sectors >> 16));
    identify_put_string(10, 10, "Z80PACK-TARGET-CF");
    identify_put_string(23, 4, "0001");
    identify_put_string(27, 20, "z80pack IMSAI Target CF");

    transfer = XFER_IDENTIFY;
    identify_pos = 0;
    ata_error = 0;
    ata_status = ATA_STATUS_DRDY | ATA_STATUS_DRQ;
    trace("IDENTIFY DEVICE");
}

static void execute_command(BYTE command)
{
    ata_status = drive_ready() ? ATA_STATUS_BSY : 0;

    switch (command) {
    case ATA_CMD_READ:
        start_file_transfer(XFER_READ, command);
        break;
    case ATA_CMD_WRITE:
        start_file_transfer(XFER_WRITE, command);
        break;
    case ATA_CMD_IDENTIFY:
        start_identify();
        break;
    case ATA_CMD_FLUSH:
        if (drive_ready() && current_drive()->writable)
            fflush(current_drive()->fp);
        ata_error = 0;
        ata_set_ready();
        break;
    case ATA_CMD_SET_FEATURE:
        /* No currently emulated feature changes affect the target software. */
        ata_error = 0;
        ata_set_ready();
        break;
    default:
        if (trace_enabled)
            fprintf(stderr, "target-ide: unsupported ATA command %02X\n",
                    command);
        ata_fail(ATA_ERROR_ABRT);
        break;
    }
}

static uint16_t read_data_word(void)
{
    int lo;
    int hi;
    uint16_t word;

    if (transfer == XFER_IDENTIFY) {
        if (identify_pos >= SECTOR_SIZE)
            return 0xffff;
        word = (uint16_t) identify_data[identify_pos] |
               ((uint16_t) identify_data[identify_pos + 1] << 8);
        identify_pos += 2;
        if (identify_pos >= SECTOR_SIZE) {
            transfer = XFER_NONE;
            ata_status = ATA_STATUS_DRDY;
        }
        return word;
    }

    if (transfer != XFER_READ || current_drive()->fp == NULL)
        return 0xffff;

    lo = fgetc(current_drive()->fp);
    hi = fgetc(current_drive()->fp);
    if (lo == EOF || hi == EOF) {
        ata_fail(ATA_ERROR_IDNF);
        return 0xffff;
    }

    word = (uint16_t) (BYTE) lo | ((uint16_t) (BYTE) hi << 8);
    if (sector_bytes_remaining >= 2)
        sector_bytes_remaining -= 2;
    if (sector_bytes_remaining == 0)
        finish_sector();
    return word;
}

static void write_data_word(uint16_t word)
{
    if (transfer != XFER_WRITE || current_drive()->fp == NULL ||
        !current_drive()->writable) {
        ata_fail(ATA_ERROR_ABRT);
        return;
    }

    if (fputc((int) (word & 0xff), current_drive()->fp) == EOF ||
        fputc((int) (word >> 8), current_drive()->fp) == EOF) {
        ata_fail(ATA_ERROR_ABRT);
        return;
    }

    if (sector_bytes_remaining >= 2)
        sector_bytes_remaining -= 2;
    if (sector_bytes_remaining == 0)
        finish_sector();
}

static BYTE read_task_register(unsigned reg)
{
    switch (reg) {
    case ATA_REG_ERROR:
        return ata_error;
    case ATA_REG_COUNT:
        return ata_count;
    case ATA_REG_SECTOR:
        return ata_sector;
    case ATA_REG_CYL_LO:
        return ata_cyl_lo;
    case ATA_REG_CYL_HI:
        return ata_cyl_hi;
    case ATA_REG_SDH:
        return ata_sdh;
    case ATA_REG_STATUS:
        return ata_status;
    default:
        return 0xff;
    }
}

static void write_task_register(unsigned reg, BYTE value)
{
    switch (reg) {
    case ATA_REG_FEATURES:
        ata_features = value;
        break;
    case ATA_REG_COUNT:
        ata_count = value;
        break;
    case ATA_REG_SECTOR:
        ata_sector = value;
        break;
    case ATA_REG_CYL_LO:
        ata_cyl_lo = value;
        break;
    case ATA_REG_CYL_HI:
        ata_cyl_hi = value;
        break;
    case ATA_REG_SDH:
        ata_sdh = value;
        break;
    case ATA_REG_COMMAND:
        execute_command(value);
        break;
    default:
        break;
    }
}

static int selected_register(BYTE c)
{
    unsigned select = c & IDE_SELECT_MASK;
    if (select < IDE_SELECT_BASE)
        return -1;
    return (int) (select - IDE_SELECT_BASE);
}

static void latch_read_cycle(BYTE c)
{
    int reg = selected_register(c);

    if (reg < 0)
        return;

    if (reg == ATA_REG_DATA) {
        uint16_t word = read_data_word();
        ppi_a = (BYTE) word;
        ppi_b = (BYTE) (word >> 8);
    } else {
        ppi_a = read_task_register((unsigned) reg);
        ppi_b = 0;
    }
}

static void latch_write_cycle(BYTE c)
{
    int reg = selected_register(c);

    if (reg < 0)
        return;

    if (reg == ATA_REG_DATA) {
        write_data_word((uint16_t) ppi_a | ((uint16_t) ppi_b << 8));
    } else {
        write_task_register((unsigned) reg, ppi_a);
    }
}

static void ata_reset(void)
{
    ata_error = 0;
    ata_features = 0;
    ata_count = 0;
    ata_sector = 1;
    ata_cyl_lo = 0;
    ata_cyl_hi = 0;
    ata_sdh = 0xe0;
    transfer = XFER_NONE;
    sectors_remaining = 0;
    sector_bytes_remaining = 0;
    identify_pos = 0;
    ata_set_ready();
}

void target_ide_init(void)
{
    const char *trace_env = getenv("TARGET_IDE_TRACE");

    trace_enabled = trace_env != NULL && *trace_env != '\0' &&
                    strcmp(trace_env, "0") != 0;
    selected_drive = 0;
    ppi_a = ppi_b = ppi_c = ppi_ctrl = 0;

    open_drive(0, "TARGET_CF0");
    open_drive(1, "TARGET_CF1");
    ata_reset();
}

void target_ide_reset(void)
{
    ata_reset();
}

void target_ide_exit(void)
{
    close_drive(&drives[0]);
    close_drive(&drives[1]);
}

BYTE target_ide_a_in(void)
{
    return ppi_a;
}

BYTE target_ide_b_in(void)
{
    return ppi_b;
}

BYTE target_ide_c_in(void)
{
    return ppi_c;
}

void target_ide_a_out(BYTE data)
{
    ppi_a = data;
}

void target_ide_b_out(BYTE data)
{
    ppi_b = data;
}

void target_ide_c_out(BYTE data)
{
    BYTE previous = ppi_c;

    ppi_c = data;

    if ((data & IDE_RESET_BIT) && !(previous & IDE_RESET_BIT)) {
        trace("hardware reset asserted");
        ata_reset();
    }

    if ((data & IDE_RD_BIT) && !(previous & IDE_RD_BIT))
        latch_read_cycle(data);

    if ((data & IDE_WR_BIT) && !(previous & IDE_WR_BIT))
        latch_write_cycle(data);
}

void target_ide_ctrl_out(BYTE data)
{
    ppi_ctrl = data;
    UNUSED(ppi_ctrl);
}

void target_ide_drive_out(BYTE data)
{
    selected_drive = data & 1;
    transfer = XFER_NONE;
    ata_set_ready();
    if (trace_enabled)
        fprintf(stderr, "target-ide: selected CF%d\n", selected_drive);
}
