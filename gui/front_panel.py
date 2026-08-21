#!/usr/bin/env python3
"""Pure helpers for the IMSAI FFH sense-switch bank."""

from __future__ import annotations

CONSOLE_NAMES = {
    0: "Console I/O",
    1: "Serial I/O A",
    2: "MIO SIO",
    3: "Reserved / Console I/O fallback",
}


def parse_hex_byte(value: str) -> int:
    parsed = int(value.strip(), 16)
    if not 0 <= parsed <= 0xFF:
        raise ValueError("value must be 00-FF")
    return parsed


def switch_states(value: int) -> dict[int, bool]:
    if not 0 <= value <= 0xFF:
        raise ValueError("value must be 00-FF")
    return {bit: bool(value & (1 << bit)) for bit in range(8)}


def value_from_states(states: dict[int, bool]) -> int:
    value = 0
    for bit in range(8):
        if states.get(bit, False):
            value |= 1 << bit
    return value


def console_name(value: int) -> str:
    return CONSOLE_NAMES[value & 0x03]
