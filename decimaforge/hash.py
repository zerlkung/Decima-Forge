"""MurmurHash3_x64_128 implementation for Decima archives.

Decima uses MurmurHash3_x64_128 with seed 0x2A (42):
- File path hashing: hash the null-terminated UTF-8 path, take low 64 bits
- Encryption key derivation: hash 16-byte descriptor blocks
- Type ID generation: hash the type name string, take low 64 bits

Credit:
  - smhasher (https://github.com/aappleby/smhasher) — MurmurHash3 reference (public domain)
  - Decima-Explorer (https://github.com/acrinym/Decima-Explorer) — hash usage in archive context
"""

import struct

C1 = 0x87C37B91114253D5
C2 = 0x4CF5AD432745937F
R1 = 31
R2 = 27
R3 = 33
M = 5
N1 = 0x52DCE729
N2 = 0x38495AB5


def _rotl64(x: int, r: int) -> int:
    return ((x << r) | (x >> (64 - r))) & 0xFFFFFFFFFFFFFFFF


def _fmix64(k: int) -> int:
    k ^= k >> 33
    k = (k * 0xFF51AFD7ED558CCD) & 0xFFFFFFFFFFFFFFFF
    k ^= k >> 33
    k = (k * 0xC4CEB9FE1A85EC53) & 0xFFFFFFFFFFFFFFFF
    k ^= k >> 33
    return k


def murmurhash3_x64_128(data: bytes, seed: int = 0x2A) -> tuple[int, int]:
    """Compute full MurmurHash3_x64_128 hash.

    Returns (h1, h2) tuple of 64-bit hash values.
    For file path hashing, only h1 (the first 64 bits) is used.
    """
    h1 = seed
    h2 = seed
    length = len(data)

    num_blocks = length // 16
    for i in range(num_blocks):
        idx = i * 16
        k1 = struct.unpack_from('<Q', data, idx)[0]
        k2 = struct.unpack_from('<Q', data, idx + 8)[0]

        k1 = (k1 * C1) & 0xFFFFFFFFFFFFFFFF
        k1 = _rotl64(k1, R1)
        k1 = (k1 * C2) & 0xFFFFFFFFFFFFFFFF
        h1 ^= k1
        h1 = _rotl64(h1, R2)
        h1 = ((h1 + h2) * M + N1) & 0xFFFFFFFFFFFFFFFF

        k2 = (k2 * C2) & 0xFFFFFFFFFFFFFFFF
        k2 = _rotl64(k2, R3)
        k2 = (k2 * C1) & 0xFFFFFFFFFFFFFFFF
        h2 ^= k2
        h2 = _rotl64(h2, R1)
        h2 = ((h2 + h1) * M + N2) & 0xFFFFFFFFFFFFFFFF

    tail = num_blocks * 16
    remaining = length - tail
    k1 = 0
    k2 = 0

    if remaining >= 8:
        k2 = struct.unpack_from('<Q', data, tail)[0]
        k2 = (k2 * C2) & 0xFFFFFFFFFFFFFFFF
        k2 = _rotl64(k2, R3)
        k2 = (k2 * C1) & 0xFFFFFFFFFFFFFFFF
        h2 ^= k2
        tail += 8
        remaining -= 8

    if remaining > 0:
        k1 = int.from_bytes(data[tail:tail + remaining], 'little')

    h1 ^= k1
    h2 ^= k2
    h1 ^= length
    h2 ^= length
    h1 = (h1 + h2) & 0xFFFFFFFFFFFFFFFF
    h2 = (h2 + h1) & 0xFFFFFFFFFFFFFFFF
    h1 = _fmix64(h1)
    h2 = _fmix64(h2)
    h1 = (h1 + h2) & 0xFFFFFFFFFFFFFFFF
    h2 = (h2 + h1) & 0xFFFFFFFFFFFFFFFF

    return h1, h2


def hash_path(path: str) -> int:
    """Hash a file path for Decima archive lookup.

    Path is normalized (backslashes → forward slashes), null-terminated,
    then hashed with MurmurHash3_x64_128(seed=42). Returns low 64 bits.
    """
    normalized = path.replace('\\', '/')
    data = normalized.encode('utf-8') + b'\x00'
    return murmurhash3_x64_128(data)[0]


def hash_type_name(name: str) -> int:
    """Hash an RTTI type name for .core file type ID lookup."""
    data = name.encode('utf-8')
    return murmurhash3_x64_128(data)[0]


def murmurhash3_x64_128_as_bytes(data: bytes, seed: int = 0x2A) -> bytes:
    """Compute MurmurHash3_x64_128 and return as 16 raw bytes (little-endian)."""
    h1, h2 = murmurhash3_x64_128(data, seed)
    return struct.pack('<QQ', h1, h2)
