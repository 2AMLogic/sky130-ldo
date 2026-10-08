"""Core-area measurement of a routed GDSII stream (issue #236).

Standard library only, so the measurement runs (and is unit-tested) under the
repo's plain `python3` with no `klayout`/`klt` install -- the same property
`measurements/build_characterization_report.py` relies on.

Convention (the ONE geometry convention this repo's Area row is judged by):

- **Footprint = the top cell's flattened bounding rectangle.** Every drawn
  shape on every layer/datatype of the top cell *and of everything it
  instantiates, recursively* (SREF and AREF, with reflection, magnification
  and rotation) contributes. Routing, rails, taps, well/marker layers and the
  pass device all count; nothing is excluded by layer. A rectangle around the
  whole cell is conservative on purpose: it charges the empty corners and the
  routing channel to the block, which is the honest cost of placing it.
- **Excluded:** TEXT labels (they have no area) and NODE records. This repo's
  core cell carries no pads or sealring, so there is nothing further to carve
  out for the spec row's "excluding pads and sealring" clause; a layout that
  later adds them must say how it excludes them in a new record.
- **PATH elements** are bounded by their vertices expanded by half the path
  width on every side. For flush-ended (pathtype 0) paths this over-counts by
  at most half a width at each end -- conservative, never optimistic.
- **Non-Manhattan transforms** (an arbitrary ANGLE, or a MAG other than 1) are
  bounded through the child cell's bounding-box corners, which can only
  over-count. Manhattan transforms are exact.
- **Units** come from the stream's own UNITS record (metres per database unit),
  never assumed to be 1 nm.
- **Threshold is strict**: `area < limit` passes; exactly the limit FAILS,
  matching the ratified row's "< 0.1 mm^2". The arithmetic is exact
  (`decimal`), so a rectangle of exactly 0.1 mm^2 cannot slip through on a
  float rounding.
"""

from __future__ import annotations

import hashlib
import math
import struct
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

# The ratified limit: spec/target-spec.md "Area" row, < 0.1 mm^2. Stated here
# in um^2 (1 mm^2 = 1e6 um^2) so the comparison needs no float conversion.
LIMIT_MM2 = Decimal("0.1")
UM2_PER_MM2 = Decimal(1_000_000)

CONVENTION = (
    "Top-cell flattened bounding rectangle over all layers/datatypes "
    "(hierarchy, SREF/AREF transforms and path widths included; TEXT and NODE "
    "excluded); area = width x height in um^2 converted to mm^2 from the "
    "stream's own UNITS record; PASS iff area < 0.1 mm^2 (strict)."
)

# GDSII record types used here.
_UNITS, _ENDLIB = 0x03, 0x04
_BGNSTR, _STRNAME, _ENDSTR = 0x05, 0x06, 0x07
_BOUNDARY, _PATH, _SREF, _AREF = 0x08, 0x09, 0x0A, 0x0B
_XY, _ENDEL, _SNAME, _COLROW = 0x10, 0x11, 0x12, 0x13
_WIDTH, _STRANS, _MAG, _ANGLE = 0x0F, 0x1A, 0x1B, 0x1C
_BOX = 0x2D
_TEXT, _NODE = 0x0C, 0x15


class GdsError(ValueError):
    """The stream is malformed or cannot be measured."""


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _real8(raw: bytes) -> float:
    """Decode a GDSII 8-byte excess-64 base-16 real."""
    sign = -1.0 if raw[0] & 0x80 else 1.0
    exp = (raw[0] & 0x7F) - 64
    mant = int.from_bytes(raw[1:8], "big") / float(1 << 56)
    return sign * mant * (16.0**exp)


def _records(data: bytes):
    pos, n = 0, len(data)
    while pos < n:
        if pos + 4 > n:
            raise GdsError("truncated record header")
        length, rtype = struct.unpack_from(">HB", data, pos)
        if length < 4 or pos + length > n:
            raise GdsError(f"bad record length {length} at offset {pos}")
        yield rtype, data[pos + 4 : pos + length]
        pos += length
    return


@dataclass
class _Ref:
    sname: str
    reflect: bool
    mag: float
    angle: float
    # SREF: one origin. AREF: origin, cols, rows, column step, row step.
    origin: tuple[int, int]
    cols: int = 1
    rows: int = 1
    col_step: tuple[float, float] = (0.0, 0.0)
    row_step: tuple[float, float] = (0.0, 0.0)


@dataclass
class _Cell:
    name: str
    bbox: tuple[int, int, int, int] | None = None  # own shapes only
    refs: list = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.refs is None:
            self.refs = []


def _grow(box, x0, y0, x1, y1):
    if box is None:
        return (x0, y0, x1, y1)
    return (min(box[0], x0), min(box[1], y0), max(box[2], x1), max(box[3], y1))


def parse(data: bytes) -> tuple[dict[str, _Cell], Decimal]:
    """Parse a stream into `{name: cell}` and the database unit in um."""
    cells: dict[str, _Cell] = {}
    dbu_um: Decimal | None = None
    cur: _Cell | None = None
    el: dict | None = None
    saw_end = False
    for rtype, body in _records(data):
        if rtype == _UNITS:
            if len(body) != 16:
                raise GdsError("bad UNITS record")
            metres = _real8(body[8:16])
            if not metres > 0:
                raise GdsError("non-positive database unit")
            # 12 significant digits strips the real-8 binary noise
            # (1e-9 is stored as 0.99999999999999...e-9).
            dbu_um = Decimal(f"{metres * 1e6:.12g}")
        elif rtype == _ENDLIB:
            saw_end = True
            break
        elif rtype == _BGNSTR:
            cur = _Cell("")
        elif rtype == _STRNAME and cur is not None and el is None:
            cur.name = body.rstrip(b"\0").decode("ascii")
        elif rtype == _ENDSTR:
            if cur is None:
                raise GdsError("ENDSTR outside a structure")
            cells[cur.name] = cur
            cur = None
        elif rtype in (_BOUNDARY, _PATH, _SREF, _AREF, _BOX, _TEXT, _NODE):
            if cur is None:
                raise GdsError("element outside a structure")
            el = {"kind": rtype, "width": 0, "xy": [], "sname": "", "reflect": False,
                  "mag": 1.0, "angle": 0.0, "colrow": (1, 1)}
        elif el is not None and rtype == _WIDTH:
            el["width"] = abs(struct.unpack(">i", body)[0])
        elif el is not None and rtype == _XY:
            vals = struct.unpack(f">{len(body) // 4}i", body)
            el["xy"] = list(zip(vals[0::2], vals[1::2]))
        elif el is not None and rtype == _SNAME:
            el["sname"] = body.rstrip(b"\0").decode("ascii")
        elif el is not None and rtype == _COLROW:
            el["colrow"] = struct.unpack(">hh", body)
        elif el is not None and rtype == _STRANS:
            el["reflect"] = bool(struct.unpack(">H", body)[0] & 0x8000)
        elif el is not None and rtype == _MAG:
            el["mag"] = _real8(body)
        elif el is not None and rtype == _ANGLE:
            el["angle"] = _real8(body)
        elif rtype == _ENDEL:
            assert cur is not None and el is not None
            kind, xy = el["kind"], el["xy"]
            if kind in (_BOUNDARY, _BOX):
                if not xy:
                    raise GdsError("boundary without XY")
                xs, ys = [p[0] for p in xy], [p[1] for p in xy]
                cur.bbox = _grow(cur.bbox, min(xs), min(ys), max(xs), max(ys))
            elif kind == _PATH:
                if not xy:
                    raise GdsError("path without XY")
                hw = (el["width"] + 1) // 2  # outward-rounded half width
                xs, ys = [p[0] for p in xy], [p[1] for p in xy]
                cur.bbox = _grow(cur.bbox, min(xs) - hw, min(ys) - hw, max(xs) + hw, max(ys) + hw)
            elif kind == _SREF:
                if len(xy) != 1:
                    raise GdsError("SREF needs exactly one XY point")
                cur.refs.append(_Ref(el["sname"], el["reflect"], el["mag"], el["angle"], xy[0]))
            elif kind == _AREF:
                if len(xy) != 3:
                    raise GdsError("AREF needs exactly three XY points")
                cols, rows = el["colrow"]
                if cols < 1 or rows < 1:
                    raise GdsError("AREF with non-positive COLROW")
                (ox, oy), (cx, cy), (rx, ry) = xy
                cur.refs.append(
                    _Ref(el["sname"], el["reflect"], el["mag"], el["angle"], (ox, oy),
                         cols, rows, ((cx - ox) / cols, (cy - oy) / cols),
                         ((rx - ox) / rows, (ry - oy) / rows))
                )
            # TEXT / NODE: deliberately contribute no area.
            el = None
    if dbu_um is None:
        raise GdsError("no UNITS record")
    if not saw_end:
        raise GdsError("no ENDLIB record (truncated stream)")
    return cells, dbu_um


def _rot(x: float, y: float, angle: float) -> tuple[float, float]:
    a = angle % 360.0
    if a == 0.0:
        return x, y
    if a == 90.0:
        return -y, x
    if a == 180.0:
        return -x, -y
    if a == 270.0:
        return y, -x
    r = math.radians(angle)
    return x * math.cos(r) - y * math.sin(r), x * math.sin(r) + y * math.cos(r)


def _place(box, ref: _Ref, dx: float, dy: float):
    """Bounding box of a child's `box` under `ref`'s transform, shifted by
    (dx, dy) (the instance offset within an array)."""
    xs, ys = [], []
    for x, y in ((box[0], box[1]), (box[0], box[3]), (box[2], box[1]), (box[2], box[3])):
        if ref.reflect:
            y = -y
        x, y = x * ref.mag, y * ref.mag
        x, y = _rot(x, y, ref.angle)
        xs.append(x + ref.origin[0] + dx)
        ys.append(y + ref.origin[1] + dy)
    return min(xs), min(ys), max(xs), max(ys)


def cell_bbox(cells: dict[str, _Cell], name: str, _memo=None, _stack=()):
    """Flattened bounding box (dbu, outward-rounded ints) or None if empty."""
    memo = {} if _memo is None else _memo
    if name in memo:
        return memo[name]
    if name in _stack:
        raise GdsError(f"cell hierarchy cycle through {name!r}")
    if name not in cells:
        raise GdsError(f"reference to undefined cell {name!r}")
    cell = cells[name]
    box = cell.bbox
    for ref in cell.refs:
        child = cell_bbox(cells, ref.sname, memo, _stack + (name,))
        if child is None:
            continue
        # Instances of an array differ only by translation, so the union is
        # the union of the four corner instances.
        for i in {0, ref.cols - 1}:
            for j in {0, ref.rows - 1}:
                dx = i * ref.col_step[0] + j * ref.row_step[0]
                dy = i * ref.col_step[1] + j * ref.row_step[1]
                x0, y0, x1, y1 = _place(child, ref, dx, dy)
                box = _grow(box, math.floor(round(x0, 6)), math.floor(round(y0, 6)),
                            math.ceil(round(x1, 6)), math.ceil(round(y1, 6)))
    memo[name] = box
    return box


def top_cells(cells: dict[str, _Cell]) -> list[str]:
    referenced = {r.sname for c in cells.values() for r in c.refs}
    return [n for n in cells if n not in referenced]


@dataclass(frozen=True)
class AreaMeasurement:
    cell: str
    bbox_dbu: tuple[int, int, int, int]
    dbu_um: Decimal
    width_um: Decimal
    height_um: Decimal
    area_um2: Decimal
    area_mm2: Decimal
    limit_mm2: Decimal
    verdict: str  # "PASS" | "FAIL"


def verdict_for(area_mm2: Decimal, limit_mm2: Decimal = LIMIT_MM2) -> str:
    """Strict: exactly the limit FAILS (spec row is '< 0.1 mm^2')."""
    return "PASS" if area_mm2 < limit_mm2 else "FAIL"


def measure_bytes(data: bytes, cell: str | None = None,
                  limit_mm2: Decimal = LIMIT_MM2) -> AreaMeasurement:
    cells, dbu_um = parse(data)
    if cell is None:
        tops = top_cells(cells)
        if len(tops) != 1:
            raise GdsError(f"expected exactly one top cell, found {sorted(tops)}; name one")
        cell = tops[0]
    box = cell_bbox(cells, cell)
    if box is None:
        raise GdsError(f"cell {cell!r} has no geometry")
    w_dbu, h_dbu = box[2] - box[0], box[3] - box[1]
    width_um, height_um = Decimal(w_dbu) * dbu_um, Decimal(h_dbu) * dbu_um
    area_um2 = width_um * height_um
    area_mm2 = area_um2 / UM2_PER_MM2
    return AreaMeasurement(cell, box, dbu_um, width_um, height_um, area_um2, area_mm2,
                           limit_mm2, verdict_for(area_mm2, limit_mm2))


def measure_file(path: Path, cell: str | None = None) -> AreaMeasurement:
    return measure_bytes(Path(path).read_bytes(), cell)
