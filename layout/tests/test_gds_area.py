"""Synthetic-geometry coverage for layout/bin/_gds_area.py (issue #236).

Builds tiny GDSII streams in memory (no klayout/klt) so each clause of the
stated area convention is pinned: hierarchy, non-unit database units, routing
outside the device bounds, rotation/array transforms, and the strict
`< 0.1 mm^2` threshold (exactly 0.1 mm^2 FAILS).
"""

from __future__ import annotations

import struct
import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bin"))
import _gds_area as ga  # noqa: E402


def _rec(rtype: int, dtype: int, payload: bytes = b"") -> bytes:
    return struct.pack(">HBB", 4 + len(payload), rtype, dtype) + payload


def _real8(v: float) -> bytes:
    if v == 0:
        return bytes(8)
    sign = 0x80 if v < 0 else 0
    v = abs(v)
    exp = 0
    while v >= 1:
        v /= 16
        exp += 1
    while v < 1 / 16:
        v *= 16
        exp -= 1
    mant = int(round(v * (1 << 56)))
    return bytes([sign | (exp + 64)]) + mant.to_bytes(7, "big")


def _i16(*v):
    return struct.pack(f">{len(v)}h", *v)


def _i32(*v):
    return struct.pack(f">{len(v)}i", *v)


def _name(rtype: int, s: str) -> bytes:
    b = s.encode()
    if len(b) % 2:
        b += b"\0"
    return _rec(rtype, 6, b)


def boundary(x0, y0, x1, y1, layer=1):
    return (_rec(0x08, 0) + _rec(0x0D, 2, _i16(layer)) + _rec(0x0E, 2, _i16(0))
            + _rec(0x10, 3, _i32(x0, y0, x1, y0, x1, y1, x0, y1, x0, y0)) + _rec(0x11, 0))


def path(pts, width, layer=2):
    xy = [c for p in pts for c in p]
    return (_rec(0x09, 0) + _rec(0x0D, 2, _i16(layer)) + _rec(0x0E, 2, _i16(0))
            + _rec(0x0F, 3, _i32(width)) + _rec(0x10, 3, _i32(*xy)) + _rec(0x11, 0))


def text(x, y):
    return (_rec(0x0C, 0) + _rec(0x0D, 2, _i16(1)) + _rec(0x16, 2, _i16(0))
            + _rec(0x10, 3, _i32(x, y)) + _name(0x19, "far away") + _rec(0x11, 0))


def sref(name, x, y, angle=None, reflect=False, mag=None):
    out = _rec(0x0A, 0) + _name(0x12, name)
    if reflect or angle is not None or mag is not None:
        out += _rec(0x1A, 1, struct.pack(">H", 0x8000 if reflect else 0))
        if mag is not None:
            out += _rec(0x1B, 5, _real8(mag))
        if angle is not None:
            out += _rec(0x1C, 5, _real8(angle))
    return out + _rec(0x10, 3, _i32(x, y)) + _rec(0x11, 0)


def aref(name, x, y, cols, rows, dx, dy):
    return (_rec(0x0B, 0) + _name(0x12, name) + _rec(0x13, 2, _i16(cols, rows))
            + _rec(0x10, 3, _i32(x, y, x + cols * dx, y, x, y + rows * dy)) + _rec(0x11, 0))


def struct_(name, *elements):
    return _rec(0x05, 2, bytes(24)) + _name(0x06, name) + b"".join(elements) + _rec(0x07, 0)


def stream(*structs, dbu_um=0.001):
    return (_rec(0x00, 2, _i16(600)) + _rec(0x01, 2, bytes(24)) + _name(0x02, "lib")
            + _rec(0x03, 5, _real8(dbu_um) + _real8(dbu_um * 1e-6))
            + b"".join(structs) + _rec(0x04, 0))


class TestMeasure(unittest.TestCase):
    def test_flat_rectangle(self):
        m = ga.measure_bytes(stream(struct_("TOP", boundary(0, 0, 10000, 20000))))
        self.assertEqual((m.width_um, m.height_um), (Decimal(10), Decimal(20)))
        self.assertEqual(m.area_um2, Decimal(200))
        self.assertEqual(m.cell, "TOP")

    def test_hierarchy_is_included(self):
        child = struct_("CHILD", boundary(0, 0, 4000, 4000))
        top = struct_("TOP", boundary(0, 0, 1000, 1000), sref("CHILD", 50000, 30000))
        m = ga.measure_bytes(stream(child, top))
        self.assertEqual((m.width_um, m.height_um), (Decimal(54), Decimal(34)))

    def test_nested_hierarchy_and_aref(self):
        leaf = struct_("LEAF", boundary(0, 0, 1000, 1000))
        mid = struct_("MID", aref("LEAF", 0, 0, 3, 2, 5000, 7000))
        top = struct_("TOP", sref("MID", 100000, 0))
        m = ga.measure_bytes(stream(leaf, mid, top))
        # array spans x: 0..(2*5000+1000), y: 0..(1*7000+1000), shifted +100000
        self.assertEqual(m.bbox_dbu, (100000, 0, 111000, 8000))

    def test_non_unit_database_units(self):
        # 5 nm database unit: the same integer box means a different size.
        s = stream(struct_("TOP", boundary(0, 0, 2000, 4000)), dbu_um=0.005)
        m = ga.measure_bytes(s)
        self.assertEqual(m.dbu_um, Decimal("0.005"))
        self.assertEqual((m.width_um, m.height_um), (Decimal(10), Decimal(20)))
        self.assertEqual(m.area_um2, Decimal(200))
        # ...and 1 nm / 10 nm units scale accordingly (not assumed to be 1 nm).
        m2 = ga.measure_bytes(stream(struct_("TOP", boundary(0, 0, 2000, 4000)), dbu_um=0.0005))
        self.assertEqual(m2.area_um2, Decimal("2"))

    def test_routing_outside_device_bounds_counts(self):
        devices = boundary(0, 0, 10000, 10000)
        wire = path([(0, -30000), (60000, -30000)], width=1000)
        m = ga.measure_bytes(stream(struct_("TOP", devices, wire)))
        # path grows by half its width on every side
        self.assertEqual(m.bbox_dbu, (-500, -30500, 60500, 10000))

    def test_routing_in_child_outside_parent_devices(self):
        rails = struct_("RAILS", path([(0, 0), (0, 90000)], width=2000))
        top = struct_("TOP", boundary(0, 0, 1000, 1000), sref("RAILS", 5000, 0))
        m = ga.measure_bytes(stream(rails, top))
        self.assertEqual(m.bbox_dbu[3], 90000 + 1000)

    def test_text_labels_do_not_count(self):
        m = ga.measure_bytes(stream(struct_("TOP", boundary(0, 0, 1000, 1000), text(900000, 900000))))
        self.assertEqual(m.bbox_dbu, (0, 0, 1000, 1000))

    def test_rotation_by_90(self):
        child = struct_("C", boundary(0, 0, 4000, 1000))
        top = struct_("TOP", sref("C", 0, 0, angle=90.0))
        m = ga.measure_bytes(stream(child, top))
        self.assertEqual(m.bbox_dbu, (-1000, 0, 0, 4000))

    def test_reflection(self):
        child = struct_("C", boundary(0, 0, 1000, 3000))
        top = struct_("TOP", sref("C", 0, 0, reflect=True))
        m = ga.measure_bytes(stream(child, top))
        self.assertEqual(m.bbox_dbu, (0, -3000, 1000, 0))

    def test_magnification(self):
        child = struct_("C", boundary(0, 0, 1000, 1000))
        top = struct_("TOP", sref("C", 0, 0, mag=2.0))
        m = ga.measure_bytes(stream(child, top))
        self.assertEqual(m.bbox_dbu, (0, 0, 2000, 2000))

    def test_ambiguous_top_cell_needs_a_name(self):
        s = stream(struct_("A", boundary(0, 0, 1, 1)), struct_("B", boundary(0, 0, 2, 2)))
        with self.assertRaises(ga.GdsError):
            ga.measure_bytes(s)
        self.assertEqual(ga.measure_bytes(s, "B").bbox_dbu, (0, 0, 2, 2))

    def test_cycle_and_missing_cell_rejected(self):
        with self.assertRaises(ga.GdsError):
            ga.measure_bytes(stream(struct_("A", sref("B", 0, 0)), struct_("B", sref("A", 0, 0))), "A")
        with self.assertRaises(ga.GdsError):
            ga.measure_bytes(stream(struct_("A", sref("NOPE", 0, 0))))

    def test_truncated_stream_rejected(self):
        with self.assertRaises(ga.GdsError):
            ga.measure_bytes(stream(struct_("A", boundary(0, 0, 1, 1)))[:-4])


class TestStrictThreshold(unittest.TestCase):
    def _square_area(self, w_um, h_um, dbu_um=0.001):
        w, h = int(Decimal(w_um) / Decimal(str(dbu_um))), int(Decimal(h_um) / Decimal(str(dbu_um)))
        return ga.measure_bytes(stream(struct_("TOP", boundary(0, 0, w, h)), dbu_um=dbu_um))

    def test_exactly_the_limit_fails(self):
        m = self._square_area(1000, 100)  # exactly 100000 um^2 = 0.1 mm^2
        self.assertEqual(m.area_mm2, Decimal("0.1"))
        self.assertEqual(m.verdict, "FAIL")

    def test_exactly_the_limit_fails_with_non_unit_dbu(self):
        m = self._square_area(1000, 100, dbu_um=0.005)
        self.assertEqual(m.area_mm2, Decimal("0.1"))
        self.assertEqual(m.verdict, "FAIL")

    def test_one_dbu_under_passes_and_over_fails(self):
        under = ga.measure_bytes(stream(struct_("TOP", boundary(0, 0, 1000000, 99999))))
        self.assertLess(under.area_mm2, Decimal("0.1"))
        self.assertEqual(under.verdict, "PASS")
        over = ga.measure_bytes(stream(struct_("TOP", boundary(0, 0, 1000000, 100001))))
        self.assertEqual(over.verdict, "FAIL")

    def test_verdict_helper_is_strict(self):
        self.assertEqual(ga.verdict_for(Decimal("0.1")), "FAIL")
        self.assertEqual(ga.verdict_for(Decimal("0.0999999")), "PASS")

    def test_sha256_file(self):
        import tempfile
        with tempfile.NamedTemporaryFile() as f:
            f.write(b"abc"); f.flush()
            self.assertEqual(ga.sha256_file(Path(f.name)),
                             "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")


if __name__ == "__main__":
    unittest.main()


class TestCommittedRecord(unittest.TestCase):
    """The committed area record must be exactly what re-measuring its own
    cited GDS gives -- the verdict is evidence, not a hand-edited claim."""

    def test_latest_area_record_reproduces(self):
        import json
        root = Path(__file__).resolve().parents[2]
        reports = root / "layout" / "ldo-core" / "reports"
        rec = json.loads((reports / (reports / "LATEST-AREA").read_text().strip() / "area.json").read_text())
        gds = root / rec["gds"]["path"]
        self.assertEqual(ga.sha256_file(gds), rec["gds"]["sha256"])
        m = ga.measure_file(gds, rec["cell"])
        self.assertEqual(str(m.area_mm2), rec["area_mm2"])
        self.assertEqual(m.verdict, rec["verdict"])
        self.assertEqual(rec["limit_mm2"], "0.1")
