"""Decima archive encryption/decryption.

Decima uses a custom XOR-based encryption scheme combining MurmurHash3_x64_128
and MD5. There are two distinct mechanisms:

1. Struct encryption: XOR 32-byte entries (header body, file entries, chunk entries)
   with keys derived from MurmurHash3_x64_128 of [key, saltA[1], saltA[2], saltA[3]].

2. Data encryption: XOR compressed chunk data with a 16-byte repeating key
   derived from MurmurHash3_x64_128 of chunk descriptor XOR saltB, then MD5.

Credit:
  - Decima-Explorer (https://github.com/acrinym/Decima-Explorer) — DecimaArchive::decrypt(), dataDecrypt()
  - decima-workshop (https://github.com/ShadelessFox/decima-workshop) — Packfile.swizzle(), ChunkEntry.swizzle(), salt constants
"""

import hashlib
import struct

from .hash import murmurhash3_x64_128

# Salt constants from decima-workshop HEADER_KEY / DATA_KEY
# Packed as two uint64 per salt (each uint64 = two uint32 LE).
HEADER_KEY_A = 0xF41CAB62FA3A9443
HEADER_KEY_B = 0xD2A89E3EF376811C
DATA_KEY_A = 0x7E159D956C084A37
DATA_KEY_B = 0x18AA7D3F3D5AF7E8


def _build_iv(key: int) -> bytes:
    """Build a 16-byte IV: [key (4 LE), HEADER_KEY_A (8 LE), HEADER_KEY_B (8 LE)]."""
    buf = bytearray(16)
    struct.pack_into('<I', buf, 0, key)
    struct.pack_into('<Q', buf, 4, HEADER_KEY_A)
    struct.pack_into('<Q', buf, 12, HEADER_KEY_B)
    return bytes(buf)


def _xor_iv(data: bytearray, iv: bytes):
    """XOR data with 16-byte IV in-place."""
    for i in range(len(data)):
        data[i] ^= iv[i % 16]


def decrypt_struct(data: bytearray, key1: int, key2: int):
    """Decrypt a 32-byte struct entry (file entry or chunk entry).

    XOR first 16 bytes with MurmurHash3_x64_128([key1, HEADER_KEY], seed=42),
    and last 16 bytes with MurmurHash3_x64_128([key2, HEADER_KEY], seed=42).

    The keys are stored in-band — they get XOR'd during decryption, so we
    must capture them first, then restore after the XOR.

    Args:
        data: 32-byte mutable buffer
        key1: First key (e.g., file entry key at offset 4)
        key2: Second key (e.g., file entry key at offset 28)
    """
    assert len(data) == 32

    iv1_bytes = _build_iv(key1)
    hash1 = murmurhash3_x64_128(iv1_bytes)
    h1_lo, h1_hi = hash1

    iv2_bytes = _build_iv(key2)
    hash2 = murmurhash3_x64_128(iv2_bytes)
    h2_lo, h2_hi = hash2

    # XOR first 16 bytes (8+8)
    cur = bytearray(data[:16])
    struct.pack_into('<Q', cur, 0, struct.unpack_from('<Q', cur, 0)[0] ^ h1_lo)
    struct.pack_into('<Q', cur, 8, struct.unpack_from('<Q', cur, 8)[0] ^ h1_hi)
    data[:16] = cur

    # XOR last 16 bytes (8+8)
    cur = bytearray(data[16:32])
    struct.pack_into('<Q', cur, 0, struct.unpack_from('<Q', cur, 0)[0] ^ h2_lo)
    struct.pack_into('<Q', cur, 8, struct.unpack_from('<Q', cur, 8)[0] ^ h2_hi)
    data[16:32] = cur


def decrypt_header_body(data: bytearray, key: int):
    """Decrypt the header body (bytes 4–35, i.e., key through maxChunkSize).

    The header key field (offset 4) is used for the first 16 bytes, and
    key+1 for the second 16 bytes.

    Note: The magic field (bytes 0–3) is NOT encrypted. The header body
    starts at byte 4 (the key field itself).

    Args:
        data: 36-byte mutable buffer (bytes 4–39 of the 40-byte header)
        key: Header key value
    """
    assert len(data) == 36

    iv1_bytes = _build_iv(key)
    hash1 = murmurhash3_x64_128(iv1_bytes)
    h1_lo, h1_hi = hash1

    iv2_bytes = _build_iv(key + 1)
    hash2 = murmurhash3_x64_128(iv2_bytes)
    h2_lo, h2_hi = hash2

    # XOR first 16 bytes of body
    cur = bytearray(data[:16])
    struct.pack_into('<Q', cur, 0, struct.unpack_from('<Q', cur, 0)[0] ^ h1_lo)
    struct.pack_into('<Q', cur, 8, struct.unpack_from('<Q', cur, 8)[0] ^ h1_hi)
    data[:16] = cur

    # XOR last 16 bytes of body (bytes 20–35)
    cur = bytearray(data[4:20])
    struct.pack_into('<Q', cur, 0, struct.unpack_from('<Q', cur, 0)[0] ^ h2_lo)
    struct.pack_into('<Q', cur, 8, struct.unpack_from('<Q', cur, 8)[0] ^ h2_hi)
    data[4:20] = cur


def decrypt_chunk_data(data: bytearray, chunk_offset: int, chunk_size: int,
                       chunk_key: int):
    """Decrypt compressed chunk data.

    Algorithm:
    1. Build 16-byte descriptor: [chunk_offset(8 LE), chunk_size(4 LE), chunk_key(4 LE)]
    2. MurmurHash3_x64_128(descriptor, seed=42) → h1, h2
    3. XOR: lo = h1 ^ DATA_KEY_A, hi = h2 ^ DATA_KEY_B
    4. MD5([lo, hi] as 16 bytes) → 16-byte digest
    5. XOR data with MD5 digest (cyclic)

    Args:
        data: Mutable compressed chunk data
        chunk_offset: Decompressed offset of this chunk
        chunk_size: Decompressed size of this chunk
        chunk_key: Chunk encryption key
    """
    descriptor = bytearray(16)
    struct.pack_into('<Q', descriptor, 0, chunk_offset)
    struct.pack_into('<I', descriptor, 8, chunk_size)
    struct.pack_into('<I', descriptor, 12, chunk_key)

    h1, h2 = murmurhash3_x64_128(bytes(descriptor))

    md5_input = struct.pack('<QQ', h1 ^ DATA_KEY_A, h2 ^ DATA_KEY_B)
    digest = hashlib.md5(md5_input).digest()

    _xor_iv(data, digest)
