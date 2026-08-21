#!/usr/bin/env python3
"""Validate and stage selectable 4K ROM images for targetsim."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

ROM_SIZE = 4096
ROM_ORIGIN = 0xF000
ROM_END = ROM_ORIGIN + ROM_SIZE
RECORD_SIZE = 16


@dataclass(frozen=True)
class RomInfo:
    path: Path
    format: str
    sha256: str

    @property
    def summary(self) -> str:
        return f"4K {self.format} ROM @ F000H · SHA256 {self.sha256[:12]}…"


def _ihex_record(address: int, record_type: int, data: bytes) -> str:
    fields = [len(data), (address >> 8) & 0xFF, address & 0xFF, record_type, *data]
    checksum = (-sum(fields)) & 0xFF
    return ":" + "".join(f"{value:02X}" for value in [*fields, checksum])


def binary_to_ihex(image: bytes) -> str:
    if len(image) != ROM_SIZE:
        raise ValueError(f"expected exactly {ROM_SIZE} bytes, got {len(image)}")
    lines = []
    for offset in range(0, ROM_SIZE, RECORD_SIZE):
        lines.append(_ihex_record(ROM_ORIGIN + offset, 0x00, image[offset : offset + RECORD_SIZE]))
    lines.append(_ihex_record(0, 0x01, b""))
    return "\n".join(lines) + "\n"


def _parse_ihex(text: str) -> dict[int, int]:
    memory: dict[int, int] = {}
    base = 0
    eof_seen = False

    for line_number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        if eof_seen:
            raise ValueError(f"Intel HEX data after EOF record at line {line_number}")
        if not line.startswith(":"):
            raise ValueError(f"invalid Intel HEX record at line {line_number}")
        try:
            record = bytes.fromhex(line[1:])
        except ValueError as exc:
            raise ValueError(f"invalid Intel HEX digits at line {line_number}") from exc
        if len(record) < 5:
            raise ValueError(f"short Intel HEX record at line {line_number}")
        count = record[0]
        if len(record) != count + 5:
            raise ValueError(f"Intel HEX byte count mismatch at line {line_number}")
        if sum(record) & 0xFF:
            raise ValueError(f"Intel HEX checksum failure at line {line_number}")

        address = (record[1] << 8) | record[2]
        record_type = record[3]
        data = record[4 : 4 + count]

        if record_type == 0x00:
            absolute = base + address
            for offset, value in enumerate(data):
                target = absolute + offset
                if target in memory:
                    raise ValueError(f"overlapping Intel HEX data at {target:04X}H")
                memory[target] = value
        elif record_type == 0x01:
            if count != 0:
                raise ValueError("invalid Intel HEX EOF record")
            eof_seen = True
        elif record_type == 0x02:
            if count != 2:
                raise ValueError("invalid Intel HEX extended-segment record")
            base = int.from_bytes(data, "big") << 4
        elif record_type == 0x04:
            if count != 2:
                raise ValueError("invalid Intel HEX extended-linear record")
            base = int.from_bytes(data, "big") << 16
        elif record_type in {0x03, 0x05}:
            # Start-address metadata does not affect ROM contents.
            continue
        else:
            raise ValueError(f"unsupported Intel HEX record type {record_type:02X}")

    if not eof_seen:
        raise ValueError("Intel HEX EOF record is missing")
    return memory


def _validated_ihex_memory(text: str) -> dict[int, int]:
    memory = _parse_ihex(text)
    expected = set(range(ROM_ORIGIN, ROM_END))
    actual = set(memory)
    if actual != expected:
        missing = len(expected - actual)
        outside = len(actual - expected)
        raise ValueError(
            f"Intel HEX must contain exactly F000H-FFFFH ({ROM_SIZE} bytes); "
            f"missing={missing}, outside={outside}"
        )
    return memory


def inspect_rom(path: str | Path) -> RomInfo:
    source = Path(path).expanduser()
    data = source.read_bytes()
    digest = sha256(data).hexdigest()

    if len(data) == ROM_SIZE:
        return RomInfo(source, "binary", digest)

    try:
        text = data.decode("ascii")
    except UnicodeDecodeError as exc:
        raise ValueError(
            f"ROM must be a {ROM_SIZE}-byte binary or Intel HEX covering F000H-FFFFH"
        ) from exc
    _validated_ihex_memory(text)
    return RomInfo(source, "Intel HEX", digest)


def stage_rom(source: str | Path, destination_dir: str | Path) -> Path:
    source_path = Path(source).expanduser().resolve()
    info = inspect_rom(source_path)
    destination = Path(destination_dir).expanduser().resolve() / "target-monitor.hex"
    destination.parent.mkdir(parents=True, exist_ok=True)

    data = source_path.read_bytes()
    if info.format == "binary":
        image = data
    else:
        # Normalize any valid Intel HEX flavor into the simple 16-bit record
        # layout already proven with z80pack's loader. This also strips optional
        # start-address metadata and extended-address records.
        memory = _validated_ihex_memory(data.decode("ascii"))
        image = bytes(memory[address] for address in range(ROM_ORIGIN, ROM_END))

    destination.write_text(binary_to_ihex(image), encoding="ascii")
    return destination
