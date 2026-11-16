"""Lossless geometry snapshots for oversized, expensive constructions.

The payload is exact EWKB, never a simplified polygon. Hashes bind both packed
bytes and decoded geometry. Precision is part of the geometry checksum; fixed
precision objects are deliberately not serialized by this adapter because WKB
alone cannot preserve their precision model.
"""
from dataclasses import dataclass
import zlib
from shapely import from_wkb, to_wkb, get_precision
from .store import canonical, digest
from .loaded_geometry import geometry_checksum


@dataclass(frozen=True)
class PackedGeometry:
    key: str
    body: bytes
    raw_size: int
    raw_sha: str
    geometry_sha: str
    seal: str

    @property
    def weight(self):
        # Only compressed bytes and small immutable metadata remain resident.
        # Native decoded geometry and raw EWKB are transient caller-owned data.
        return len(self.body) + 1024

    def header(self):
        return canonical([self.key, digest(self.body), self.raw_size,
                          self.raw_sha, self.geometry_sha])

    def validate(self):
        if self.raw_size < 0 or digest(self.header()) != self.seal:
            raise ValueError('PACKED_GEOMETRY_CORRUPTED')

    @classmethod
    def pack(cls, key, shape):
        if get_precision(shape) != 0:
            return None
        raw = to_wkb(shape, include_srid=True)
        row = cls(key, zlib.compress(raw, 1), len(raw), digest(raw),
                  geometry_checksum(shape), '')
        return cls(row.key, row.body, row.raw_size, row.raw_sha,
                   row.geometry_sha, digest(row.header()))

    def restore(self):
        self.validate()
        decoder = zlib.decompressobj()
        try:
            # Bound output by the size recorded at construction. Trailing,
            # truncated or oversized payloads fail; no silent fallback.
            raw = decoder.decompress(self.body, self.raw_size + 1)
        except zlib.error as error:
            raise ValueError('PACKED_GEOMETRY_CORRUPTED') from error
        if (len(raw) != self.raw_size or not decoder.eof or decoder.unused_data
                or decoder.unconsumed_tail or digest(raw) != self.raw_sha):
            raise ValueError('PACKED_GEOMETRY_CORRUPTED')
        shape = from_wkb(raw)
        if geometry_checksum(shape) != self.geometry_sha:
            raise ValueError('PACKED_GEOMETRY_RESTORE_CHANGED')
        return shape
