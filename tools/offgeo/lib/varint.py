"""LEB128-style unsigned varint + zigzag signed-varint encoding, stdlib-
only. Used by `tools/offgeo/prototype-pack-formats.py`'s custom binary
format candidate (`OFF-104`) -- the same encoding style `spec.md` and
`roadmap.md` describe as a real candidate ("improve dictionaries/
varints" is explicitly listed as an R1 size-reduction lever). Kept as
its own small module, not inlined in the prototype script, since a real
R2 compiler/runtime would need the identical encoding on both the
Python (or whatever R1 selects) compiler side and the browser JS reader
side -- this is the reference implementation either would be checked
against.
"""
from __future__ import annotations


def write_uvarint(value: int) -> bytes:
    """Encode a non-negative integer as an unsigned LEB128 varint."""
    if value < 0:
        raise ValueError(f"write_uvarint requires a non-negative value, got {value}")
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def read_uvarint(buf: bytes, offset: int) -> tuple[int, int]:
    """Decode one unsigned varint starting at `offset`. Returns
    (value, new_offset)."""
    result = 0
    shift = 0
    while True:
        byte = buf[offset]
        offset += 1
        result |= (byte & 0x7F) << shift
        if not (byte & 0x80):
            return result, offset
        shift += 7


def zigzag_encode(value: int) -> int:
    """Map a signed integer to an unsigned one so small-magnitude
    negatives stay small-varint-encodable (standard protobuf-style
    zigzag: 0,-1,1,-2,2,... -> 0,1,2,3,4,...)."""
    return (value << 1) ^ (value >> 63) if value < 0 else (value << 1)


def zigzag_decode(value: int) -> int:
    return (value >> 1) ^ -(value & 1)


def write_svarint(value: int) -> bytes:
    return write_uvarint(zigzag_encode(value))


def read_svarint(buf: bytes, offset: int) -> tuple[int, int]:
    raw, offset = read_uvarint(buf, offset)
    return zigzag_decode(raw), offset
