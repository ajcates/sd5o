"""Unit tests for tools/offgeo/lib/dbf.py against a small hand-built DBF
byte buffer -- these scripts have previously only been exercised against
the real ~560 MB retained Address_Points.dbf archive, so this is the first
test that can run without those bytes present (OFF-012, Group 6)."""
import io
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools" / "offgeo"))

from lib import dbf  # noqa: E402


def build_dbf(fields, rows):
    """fields: list of (name, type, length). rows: list of dict OR the
    string b"*"-deleted marker value for that row's first field slot is
    handled by passing a plain string instead of a dict."""
    record_size = 1 + sum(length for _, _, length in fields)
    header_size = 32 + 32 * len(fields) + 1

    header = bytearray(32)
    header[0] = 0x03
    struct.pack_into("<I", header, 4, len(rows))
    struct.pack_into("<H", header, 8, header_size)
    struct.pack_into("<H", header, 10, record_size)

    field_descs = bytearray()
    for name, ftype, length in fields:
        desc = bytearray(32)
        name_bytes = name.encode("ascii")[:11]
        desc[0:len(name_bytes)] = name_bytes
        desc[11] = ord(ftype)
        desc[16] = length
        desc[17] = 0
        field_descs += desc

    out = bytearray()
    out += header
    out += field_descs
    out += b"\r"

    for row in rows:
        if row == "DELETED":
            out += b"*" + b" " * (record_size - 1)
            continue
        out += b" "
        for name, _ftype, length in fields:
            value = str(row.get(name, "")).encode("ascii")
            out += value.ljust(length)[:length]
    return bytes(out)


class DbfTests(unittest.TestCase):
    def test_header_and_records_roundtrip(self):
        fields = [("NAME", "C", 10), ("NUM", "N", 3)]
        rows = [{"NAME": "ALICE", "NUM": "123"}, {"NAME": "BOB", "NUM": "42"}]
        blob = build_dbf(fields, rows)

        header, records = dbf.open_dbf(io.BytesIO(blob))

        self.assertEqual(header.record_count, 2)
        self.assertEqual([f.name for f in header.fields], ["NAME", "NUM"])
        self.assertEqual([f.type for f in header.fields], ["C", "N"])

        parsed = list(records)
        self.assertEqual(parsed, [{"NAME": "ALICE", "NUM": "123"}, {"NAME": "BOB", "NUM": "42"}])

    def test_deleted_record_is_skipped(self):
        fields = [("NAME", "C", 5)]
        rows = [{"NAME": "KEEP"}, "DELETED", {"NAME": "ALSO"}]
        blob = build_dbf(fields, rows)

        header, records = dbf.open_dbf(io.BytesIO(blob))
        self.assertEqual(header.record_count, 3)  # header count includes the deleted row
        parsed = list(records)
        self.assertEqual(parsed, [{"NAME": "KEEP"}, {"NAME": "ALSO"}])

    def test_truncated_file_stops_without_raising(self):
        fields = [("NAME", "C", 5)]
        rows = [{"NAME": "FULL1"}, {"NAME": "FULL2"}]
        blob = build_dbf(fields, rows)
        truncated = blob[: len(blob) - 3]  # cut into the second record

        header, records = dbf.open_dbf(io.BytesIO(truncated))
        self.assertEqual(header.record_count, 2)
        parsed = list(records)
        self.assertEqual(parsed, [{"NAME": "FULL1"}])  # second record silently stopped, not raised


if __name__ == "__main__":
    unittest.main()
