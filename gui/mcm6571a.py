"""Motorola MCM6571A 7x9 character generator used by the Poly VTI.

The PolyMorphic Video Terminal Interface manual (Appendix B) documents the
MCM6571A character patterns and describes a 7x9 glyph in a 10x15 display cell.
The bitmap values in mcm6571a_font.dat are the MIT-licensed transcription from
paulscottrobson/1k-coding-challenge (__font7x9_mcmfont.h), cross-checked against
the Poly manual.  The descender/shift table follows MAME's BSD-3-Clause Poly
VTI implementation.
"""

from __future__ import annotations

from pathlib import Path

ROWS_PER_GLYPH = 9
GLYPH_COUNT = 128
CELL_DOTS_X = 10
CELL_DOTS_Y = 15

# MCM6571A shifted-character flags.  A set entry moves the 7x9 matrix down
# three scan lines in the 15-scan-line character cell (g, j, p, q, y, etc.).
_SHIFTED = (
    0,1,1,0,0,0,1,0,0,0,0,1,0,0,0,0,
    1,0,0,0,0,0,1,0,0,0,0,0,0,0,0,0,
    0,0,0,0,0,0,0,0,0,0,0,0,1,0,0,0,
    0,0,0,0,0,0,0,0,0,0,0,1,0,0,0,0,
    0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
    0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
    0,0,0,0,0,0,0,1,0,0,1,0,0,0,0,0,
    1,1,0,0,0,0,0,0,0,1,0,0,0,0,0,0,
)

_DATA_PATH = Path(__file__).with_name("mcm6571a_font.dat")
_FONT = tuple(
    int(value)
    for value in _DATA_PATH.read_text(encoding="ascii").replace("\n", "").split(",")
    if value.strip()
)

if len(_FONT) != GLYPH_COUNT * ROWS_PER_GLYPH:
    raise RuntimeError(
        f"MCM6571A font data has {len(_FONT)} bytes; expected "
        f"{GLYPH_COUNT * ROWS_PER_GLYPH}"
    )


def glyph_rows(code: int) -> tuple[int, ...]:
    """Return the nine raw 7-bit row patterns for one character code."""
    code &= 0x7F
    start = code * ROWS_PER_GLYPH
    return _FONT[start : start + ROWS_PER_GLYPH]


def scanline(code: int, scan: int) -> int:
    """Return the raw seven-pixel row for one of the 15 VTI scan lines.

    The data occupies bits 7..1, matching the original transcription and
    MAME's renderer.  Bit 7 is the leftmost displayed pixel.
    """
    code &= 0x7F
    if not 0 <= scan < CELL_DOTS_Y:
        return 0

    row = scan - 3 if _SHIFTED[code] else scan
    if not 0 <= row < ROWS_PER_GLYPH:
        return 0
    return _FONT[code * ROWS_PER_GLYPH + row]
