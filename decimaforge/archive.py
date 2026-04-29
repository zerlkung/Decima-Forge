""".bin archive read/write for Decima Engine.

Archive layout:
    [Header: 40 bytes]
    [File Table: N x 32 bytes]
    [Chunk Table: M x 32 bytes]
    [Chunk Data: variable]

Header (40 bytes):
    0-3   magic: uint32 (0x20304050=plain, 0x21304050=encrypted)
    4-7   key: uint32
    8-15  fileSize: uint64
    16-23 dataSize: uint64 (total uncompressed)
    24-31 fileEntryCount: uint64
    32-35 chunkEntryCount: uint32
    36-39 maxChunkSize: uint32 (typically 0x40000)

File Entry (32 bytes):
    0-3   index: uint32
    4-7   key: uint32
    8-15  hash: uint64 (MurmurHash3_x64_128 of path, low 64 bits)
    16-23 offset: uint64 (in uncompressed data stream)
    24-27 size: uint32
    28-31 key2: uint32

Chunk Entry (32 bytes):
    0-7   uncompressedOffset: uint64
    8-11  uncompressedSize: uint32
    12-15 key: uint32
    16-23 compressedOffset: uint64
    24-27 compressedSize: uint32
    28-31 key2: uint32

Credit:
  - Decima-Explorer (https://github.com/acrinym/Decima-Explorer) — archive structure, chunk layout, extraction logic
  - decima-workshop (https://github.com/ShadelessFox/decima-workshop) — file table layout, struct sizes
"""

import io
import json
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO, Optional

from .compression import OodleKraken, get_oodle
from .encryption import (
    decrypt_struct,
    decrypt_header_body,
    decrypt_chunk_data,
    HEADER_KEY_A,
    HEADER_KEY_B,
)
from .hash import hash_path, murmurhash3_x64_128

MAGIC_PLAIN = 0x20304050
MAGIC_ENCRYPTED = 0x21304050
HEADER_SIZE = 40
FILE_ENTRY_SIZE = 32
CHUNK_ENTRY_SIZE = 32


def _is_encrypted(magic: int) -> bool:
    return (magic & 0x0F000000) != 0


@dataclass
class ChunkEntry:
    uncompressed_offset: int
    uncompressed_size: int
    key: int
    compressed_offset: int
    compressed_size: int
    key2: int


@dataclass
class FileEntry:
    index: int
    key: int
    hash: int
    offset: int
    size: int
    key2: int


class DecimaArchive:
    """Read/write Decima .bin archives."""

    def __init__(self, path: str | Path, oodle: Optional[OodleKraken] = None):
        self.path = Path(path)
        self.magic = MAGIC_PLAIN
        self.key = 0
        self.file_size = 0
        self.data_size = 0
        self.max_chunk_size = 0x40000
        self.file_entries: list[FileEntry] = []
        self.chunk_entries: list[ChunkEntry] = []
        self._oodle = oodle

    @property
    def oodle(self) -> OodleKraken:
        if self._oodle is None:
            self._oodle = get_oodle()
        return self._oodle

    @property
    def is_encrypted(self) -> bool:
        return _is_encrypted(self.magic)

    @property
    def file_count(self) -> int:
        return len(self.file_entries)

    @property
    def chunk_count(self) -> int:
        return len(self.chunk_entries)

    # ── Read ──────────────────────────────────────────────

    def read(self) -> None:
        """Parse archive header and tables."""
        with open(self.path, 'rb') as f:
            self._read_header(f)
            self._read_tables(f)

    def _read_header(self, f: BinaryIO) -> None:
        raw = f.read(HEADER_SIZE)
        if len(raw) < HEADER_SIZE:
            raise ValueError(f"File too small: {len(raw)} bytes")

        self.magic = struct.unpack_from('<I', raw, 0)[0]

        # Decrypt header body if needed
        body = bytearray(raw[4:40])
        if _is_encrypted(self.magic):
            decrypt_header_body(body, struct.unpack_from('<I', body, 0)[0])

        self.key = struct.unpack_from('<I', bytes(body), 0)[0]
        self.file_size = struct.unpack_from('<Q', bytes(body), 4)[0]
        self.data_size = struct.unpack_from('<Q', bytes(body), 12)[0]
        file_entry_count = struct.unpack_from('<Q', bytes(body), 20)[0]
        chunk_entry_count = struct.unpack_from('<I', bytes(body), 28)[0]
        self.max_chunk_size = struct.unpack_from('<I', bytes(body), 32)[0]

        self._file_entry_count = file_entry_count
        self._chunk_entry_count = chunk_entry_count

    def _read_tables(self, f: BinaryIO) -> None:
        for _ in range(self._file_entry_count):
            raw = bytearray(f.read(FILE_ENTRY_SIZE))
            if len(raw) < FILE_ENTRY_SIZE:
                raise ValueError("Truncated file table")

            if _is_encrypted(self.magic):
                key1 = struct.unpack_from('<I', bytes(raw), 4)[0]
                key2 = struct.unpack_from('<I', bytes(raw), 28)[0]
                decrypt_struct(raw, key1, key2)
                # Restore original keys (they were XOR'd during decryption)
                struct.pack_into('<I', raw, 4, key1)
                struct.pack_into('<I', raw, 28, key2)

            self.file_entries.append(FileEntry(
                index=struct.unpack_from('<I', bytes(raw), 0)[0],
                key=struct.unpack_from('<I', bytes(raw), 4)[0],
                hash=struct.unpack_from('<Q', bytes(raw), 8)[0],
                offset=struct.unpack_from('<Q', bytes(raw), 16)[0],
                size=struct.unpack_from('<I', bytes(raw), 24)[0],
                key2=struct.unpack_from('<I', bytes(raw), 28)[0],
            ))

        for _ in range(self._chunk_entry_count):
            raw = bytearray(f.read(CHUNK_ENTRY_SIZE))
            if len(raw) < CHUNK_ENTRY_SIZE:
                raise ValueError("Truncated chunk table")

            if _is_encrypted(self.magic):
                key1 = struct.unpack_from('<I', bytes(raw), 12)[0]
                key2 = struct.unpack_from('<I', bytes(raw), 28)[0]
                decrypt_struct(raw, key1, key2)
                struct.pack_into('<I', raw, 12, key1)
                struct.pack_into('<I', raw, 28, key2)

            self.chunk_entries.append(ChunkEntry(
                uncompressed_offset=struct.unpack_from('<Q', bytes(raw), 0)[0],
                uncompressed_size=struct.unpack_from('<I', bytes(raw), 8)[0],
                key=struct.unpack_from('<I', bytes(raw), 12)[0],
                compressed_offset=struct.unpack_from('<Q', bytes(raw), 16)[0],
                compressed_size=struct.unpack_from('<I', bytes(raw), 24)[0],
                key2=struct.unpack_from('<I', bytes(raw), 28)[0],
            ))

        # Calculate data start offset
        self._data_start = (
            HEADER_SIZE
            + self._file_entry_count * FILE_ENTRY_SIZE
            + self._chunk_entry_count * CHUNK_ENTRY_SIZE
        )

    @classmethod
    def open(cls, path: str | Path, oodle: Optional[OodleKraken] = None) -> 'DecimaArchive':
        archive = cls(path, oodle)
        archive.read()
        return archive

    # ── Lookup ────────────────────────────────────────────

    def find_file(self, hash_val: int) -> Optional[FileEntry]:
        # File entries may not be sorted; linear scan for simplicity
        for entry in self.file_entries:
            if entry.hash == hash_val:
                return entry
        return None

    def find_file_by_path(self, path: str) -> Optional[FileEntry]:
        return self.find_file(hash_path(path))

    def get_hash_map(self) -> dict[int, FileEntry]:
        return {e.hash: e for e in self.file_entries}

    # ── Extract ───────────────────────────────────────────

    def extract(self, entry: FileEntry) -> bytes:
        """Extract and decompress a single file from the archive."""
        return self._extract_range(entry.offset, entry.size)

    def extract_by_hash(self, hash_val: int) -> Optional[bytes]:
        entry = self.find_file(hash_val)
        return self.extract(entry) if entry else None

    def extract_by_path(self, path: str) -> Optional[bytes]:
        entry = self.find_file_by_path(path)
        return self.extract(entry) if entry else None

    def _extract_range(self, file_offset: int, file_size: int) -> bytes:
        """Extract a byte range spanning one or more chunks."""
        file_end = file_offset + file_size

        # Find chunks that cover this range
        covering = []
        for chunk in self.chunk_entries:
            chunk_end = chunk.uncompressed_offset + chunk.uncompressed_size
            if chunk.uncompressed_offset < file_end and chunk_end > file_offset:
                covering.append(chunk)

        if not covering:
            raise ValueError(f"No chunks cover offset {file_offset} size {file_size}")

        # Decompress and concatenate
        decompressed_parts = []
        with open(self.path, 'rb') as f:
            for chunk in covering:
                f.seek(chunk.compressed_offset)
                compressed = bytearray(f.read(chunk.compressed_size))

                if _is_encrypted(self.magic):
                    decrypt_chunk_data(
                        compressed,
                        chunk.uncompressed_offset,
                        chunk.uncompressed_size,
                        chunk.key,
                    )

                decompressed = self.oodle.decompress(
                    bytes(compressed), chunk.uncompressed_size
                )
                decompressed_parts.append(decompressed)

        full = b''.join(decompressed_parts)

        # Slice out the exact file portion
        start_in_full = file_offset - covering[0].uncompressed_offset
        return full[start_in_full:start_in_full + file_size]

    # ── Unpack ────────────────────────────────────────────

    def unpack_all(self, out_dir: str | Path,
                   file_names: Optional[dict[int, str]] = None) -> dict:
        """Extract all files to a directory.

        Args:
            out_dir: Output directory
            file_names: Optional dict mapping hash → filename for naming

        Returns:
            Manifest dict with extraction metadata
        """
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        files_meta = []
        for entry in self.file_entries:
            try:
                data = self.extract(entry)
            except Exception as e:
                print(f"  SKIP {entry.hash:016x}: {e}")
                continue

            if file_names and entry.hash in file_names:
                filename = file_names[entry.hash]
            else:
                filename = f"{entry.hash:016x}"

            filepath = out_dir / filename
            filepath.parent.mkdir(parents=True, exist_ok=True)
            filepath.write_bytes(data)

            files_meta.append({
                'hash': entry.hash,
                'offset': entry.offset,
                'size': entry.size,
                'filename': filename,
            })

        manifest = {
            'archive': str(self.path),
            'magic': f'{self.magic:#010x}',
            'encrypted': self.is_encrypted,
            'file_count': len(files_meta),
            'chunk_count': self.chunk_count,
            'max_chunk_size': self.max_chunk_size,
            'data_size': self.data_size,
            'files': files_meta,
        }

        manifest_path = out_dir / 'manifest.json'
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')

        return manifest

    # ── Build (repack) ────────────────────────────────────

    @classmethod
    def build(cls, files: list[tuple[int, bytes]], output: str | Path,
              oodle: Optional[OodleKraken] = None,
              max_chunk_size: int = 0x40000,
              encrypt: bool = False) -> 'DecimaArchive':
        """Build a new archive from files.

        Args:
            files: List of (hash, data) tuples
            output: Output .bin file path
            oodle: OodleKraken instance
            max_chunk_size: Maximum uncompressed chunk size
            encrypt: Whether to encrypt (stub — encryption keys need generation)

        Returns:
            DecimaArchive for the newly created archive
        """
        output = Path(output)
        oodle = oodle or get_oodle()

        # Build uncompressed stream
        file_entries = []
        uncompressed = bytearray()
        for hash_val, data in files:
            offset = len(uncompressed)
            uncompressed.extend(data)
            file_entries.append(FileEntry(
                index=len(file_entries),
                key=0,
                hash=hash_val,
                offset=offset,
                size=len(data),
                key2=0,
            ))

        # Split into chunks and compress
        chunk_entries = []
        compressed_data = bytearray()

        for offset in range(0, len(uncompressed), max_chunk_size):
            chunk_data = bytes(uncompressed[offset:offset + max_chunk_size])
            compressed = oodle.compress(chunk_data)
            chunk_entries.append(ChunkEntry(
                uncompressed_offset=offset,
                uncompressed_size=len(chunk_data),
                key=0,
                compressed_offset=len(compressed_data),
                compressed_size=len(compressed),
                key2=0,
            ))
            compressed_data.extend(compressed)

        # Calculate sizes
        data_start = (
            HEADER_SIZE
            + len(file_entries) * FILE_ENTRY_SIZE
            + len(chunk_entries) * CHUNK_ENTRY_SIZE
        )
        total_size = data_start + len(compressed_data)

        # Write archive
        with open(output, 'wb') as f:
            # Header
            magic = MAGIC_ENCRYPTED if encrypt else MAGIC_PLAIN
            f.write(struct.pack('<I', magic))
            f.write(struct.pack('<I', 0))  # key
            f.write(struct.pack('<Q', total_size))
            f.write(struct.pack('<Q', len(uncompressed)))
            f.write(struct.pack('<Q', len(file_entries)))
            f.write(struct.pack('<I', len(chunk_entries)))
            f.write(struct.pack('<I', max_chunk_size))

            # File table
            for entry in file_entries:
                f.write(struct.pack('<I', entry.index))
                f.write(struct.pack('<I', entry.key))
                f.write(struct.pack('<Q', entry.hash))
                f.write(struct.pack('<Q', entry.offset))
                f.write(struct.pack('<I', entry.size))
                f.write(struct.pack('<I', entry.key2))

            # Chunk table
            for chunk in chunk_entries:
                f.write(struct.pack('<Q', chunk.uncompressed_offset))
                f.write(struct.pack('<I', chunk.uncompressed_size))
                f.write(struct.pack('<I', chunk.key))
                f.write(struct.pack('<Q', chunk.compressed_offset + data_start))
                f.write(struct.pack('<I', chunk.compressed_size))
                f.write(struct.pack('<I', chunk.key2))

            # Compressed data
            f.write(compressed_data)

        # Convert chunk offsets from relative to absolute
        for chunk in chunk_entries:
            chunk.compressed_offset += data_start

        archive = cls(output, oodle)
        archive.magic = magic
        archive.key = 0
        archive.file_size = total_size
        archive.data_size = len(uncompressed)
        archive.max_chunk_size = max_chunk_size
        archive.file_entries = file_entries
        archive.chunk_entries = chunk_entries
        archive._data_start = data_start
        archive._file_entry_count = len(file_entries)
        archive._chunk_entry_count = len(chunk_entries)
        return archive
