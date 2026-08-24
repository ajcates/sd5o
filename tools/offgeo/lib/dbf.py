"""Minimal streaming reader for the classic .dbf (dBase III/IV) format used
inside ESRI shapefiles. Stdlib-only and deliberately dependency-free: R0 is
profiling source schemas, not committing to a compiler toolchain (that's
OFF-012), and these attribute tables are large enough (Address_Points.dbf is
~560 MB uncompressed) that everything here is a forward-only generator, never
a full in-memory load.

Only the subset of the DBF spec that ESRI shapefiles actually use is
implemented: field types C (character), N (numeric, ASCII text), F (float),
D (date, YYYYMMDD), L (logical). Deleted records (leading 0x2A) are skipped.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import BinaryIO, Iterator


@dataclass
class DbfField:
    name: str
    type: str
    length: int
    decimal_count: int


@dataclass
class DbfHeader:
    record_count: int
    header_size: int
    record_size: int
    fields: list[DbfField]


def read_header(stream: BinaryIO) -> DbfHeader:
    raw = stream.read(32)
    if len(raw) < 32:
        raise ValueError("truncated DBF header")
    record_count = struct.unpack_from("<I", raw, 4)[0]
    header_size = struct.unpack_from("<H", raw, 8)[0]
    record_size = struct.unpack_from("<H", raw, 10)[0]

    fields: list[DbfField] = []
    remaining = header_size - 32
    while remaining > 1:
        desc = stream.read(32)
        remaining -= 32
        if desc[0:1] == b"\r":
            break
        name = desc[0:11].split(b"\x00", 1)[0].decode("ascii", errors="replace")
        ftype = desc[11:12].decode("ascii", errors="replace")
        length = desc[16]
        decimal_count = desc[17]
        fields.append(DbfField(name=name, type=ftype, length=length, decimal_count=decimal_count))

    # Consume any remaining header padding up to the terminator (0x0D) so the
    # stream position lands exactly at the first record.
    consumed = 32 + sum(32 for _ in fields)
    pad = header_size - consumed
    if pad > 0:
        stream.read(pad)

    return DbfHeader(record_count=record_count, header_size=header_size, record_size=record_size, fields=fields)


def iter_records(stream: BinaryIO, header: DbfHeader) -> Iterator[dict[str, str]]:
    """Yield each non-deleted record as {field_name: raw_stripped_string}.

    Values are returned as-is (stripped ASCII text) -- callers decide how to
    parse numeric/date fields, since R0 profiling cares about raw source
    forms (e.g. non-digit house-number ranges) rather than a coerced type.
    """
    for _ in range(header.record_count):
        record = stream.read(header.record_size)
        if len(record) < header.record_size:
            return  # truncated file; stop rather than raise mid-scan
        if record[0:1] == b"*":
            continue  # deleted record
        offset = 1
        row: dict[str, str] = {}
        for field in header.fields:
            raw = record[offset:offset + field.length]
            offset += field.length
            row[field.name] = raw.decode("latin-1").strip()
        yield row


def open_dbf(stream: BinaryIO) -> tuple[DbfHeader, Iterator[dict[str, str]]]:
    header = read_header(stream)
    return header, iter_records(stream, header)
