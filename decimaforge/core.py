""".core binary file format parser for Decima Engine.

A .core file is a sequence of serialized RTTI objects ("chunks"):
    [typeId: uint64 LE][chunkSize: uint32 LE][data: chunkSize bytes]

Core types used:
- BaseString: [len: uint32][crc32c: uint32][utf8: len bytes]
- GGUUID: 16 raw bytes
- BaseArray<T>: [count: uint32][items...]
- BaseRef: [type: uint8][payload varies]

This module provides a lightweight parser focused on localization and font data.
It does NOT implement full RTTI deserialization — unknown chunks pass through
as raw bytes for lossless round-tripping.

Credit:
  - HZDCoreEditor (https://github.com/Nukem9/HZDCoreE) — .core format research, RTTI type system, base types
  - Decima-Explorer (https://github.com/acrinym/Decima-Explorer) — chunk layout, type ID hashing
  - decima-workshop (https://github.com/ShadelessFox/decima-workshop) — type IDs, language order
"""

import io
import struct
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional

from .hash import murmurhash3_x64_128

# ── CRC32-C (Castagnoli) ─────────────────────────────────

_CRC32C_TABLE: list[int] = []


def _make_crc32c_table():
    global _CRC32C_TABLE
    if _CRC32C_TABLE:
        return
    poly = 0x82F63B78
    for i in range(256):
        crc = i
        for _ in range(8):
            crc = (crc >> 1) ^ poly if crc & 1 else crc >> 1
        _CRC32C_TABLE.append(crc & 0xFFFFFFFF)


def crc32c(data: bytes) -> int:
    _make_crc32c_table()
    crc = 0
    for b in data:
        crc = _CRC32C_TABLE[(crc ^ b) & 0xFF] ^ (crc >> 8)
    return crc


# ── Known Type IDs ───────────────────────────────────────

def _type_id(name: str) -> int:
    return murmurhash3_x64_128(name.encode('utf-8'))[0]


# HZD type IDs (pre-computed)
TYPE_REF = _type_id("Ref")
TYPE_ARRAY = _type_id("Array")
TYPE_STRING = _type_id("String")
TYPE_LOCALIZED_TEXT = 0xB89A596B420BB2E2       # HZD LocalizedTextResource
TYPE_TEXTURE = 0xF2E1AFB7052B3866               # HZD Texture
TYPE_UI_TEXTURE = 0x9C78E9FDC6042A60            # HZD UITexture
TYPE_TEXTURE_LIST = 0x321F4B133D40A266          # HZD TextureList
TYPE_PREFETCH_LIST = 0xF34A76FAD0A1E0D7         # HZD PrefetchList


class RefType(IntEnum):
    NULL = 0
    INTERNAL = 1
    EXTERNAL = 2
    STREAMING = 3
    UUID = 5


# ── Chunk ────────────────────────────────────────────────

@dataclass
class CoreChunk:
    """A single serialized RTTI object from a .core file."""
    type_id: int
    data: bytes  # raw chunk data (the ChunkSize bytes after the header)

    @classmethod
    def read(cls, f: io.BytesIO) -> Optional['CoreChunk']:
        header = f.read(12)
        if len(header) < 12:
            return None
        type_id = struct.unpack_from('<Q', header, 0)[0]
        size = struct.unpack_from('<I', header, 8)[0]
        data = f.read(size)
        if len(data) < size:
            raise ValueError(f"Truncated chunk: expected {size}, got {len(data)}")
        return cls(type_id=type_id, data=data)

    def write(self, f: io.BytesIO) -> None:
        f.write(struct.pack('<QI', self.type_id, len(self.data)))
        f.write(self.data)


# ── Base Types ───────────────────────────────────────────

@dataclass
class ParsedString:
    value: str
    raw_length: int  # byte length (not character count)

    @classmethod
    def read(cls, f: io.BytesIO) -> 'ParsedString':
        start = f.tell()
        length = struct.unpack('<I', f.read(4))[0]
        if length == 0:
            return cls(value='', raw_length=0)
        _checksum = struct.unpack('<I', f.read(4))[0]  # CRC32C, ignored on read
        value = f.read(length).decode('utf-8', errors='replace')
        return cls(value=value, raw_length=length)

    def write(self, f: io.BytesIO) -> None:
        encoded = self.value.encode('utf-8')
        f.write(struct.pack('<I', len(encoded)))
        if len(encoded) > 0:
            cs = crc32c(encoded) & ~0x80000000
            f.write(struct.pack('<I', cs))
            f.write(encoded)


@dataclass
class ParsedUUID:
    data: bytes  # 16 bytes

    @classmethod
    def read(cls, f: io.BytesIO) -> 'ParsedUUID':
        return cls(data=f.read(16))

    def write(self, f: io.BytesIO) -> None:
        f.write(self.data)


@dataclass
class ParsedRef:
    ref_type: RefType
    uuid: Optional[bytes] = None
    path: Optional[str] = None

    @classmethod
    def read(cls, f: io.BytesIO) -> 'ParsedRef':
        ref_type = RefType(f.read(1)[0])
        if ref_type == RefType.NULL:
            return cls(ref_type=ref_type)
        elif ref_type in (RefType.INTERNAL, RefType.UUID):
            uuid = f.read(16)
            return cls(ref_type=ref_type, uuid=uuid)
        elif ref_type in (RefType.EXTERNAL, RefType.STREAMING):
            uuid = f.read(16)
            path = _read_string_raw(f)
            return cls(ref_type=ref_type, uuid=uuid, path=path)
        return cls(ref_type=ref_type)

    def write(self, f: io.BytesIO) -> None:
        f.write(bytes([self.ref_type]))
        if self.ref_type == RefType.NULL:
            return
        if self.uuid:
            f.write(self.uuid)
        if self.path is not None:
            parsed = ParsedString(value=self.path)
            parsed.write(f)


def _read_string_raw(f: io.BytesIO) -> str:
    pos = f.tell()
    length = struct.unpack('<I', f.read(4))[0]
    if length == 0:
        return ''
    f.seek(4, 1)  # skip CRC32C
    value = f.read(length).decode('utf-8', errors='replace')
    return value


# ── Core File ────────────────────────────────────────────

@dataclass
class CoreFile:
    """Parsed .core file containing multiple chunks."""
    chunks: list[CoreChunk]

    @classmethod
    def read(cls, data: bytes) -> 'CoreFile':
        f = io.BytesIO(data)
        chunks = []
        while True:
            chunk = CoreChunk.read(f)
            if chunk is None:
                break
            chunks.append(chunk)
        return cls(chunks=chunks)

    def write(self) -> bytes:
        f = io.BytesIO()
        for chunk in self.chunks:
            chunk.write(f)
        return f.getvalue()

    def find_chunks(self, type_id: int) -> list[CoreChunk]:
        return [c for c in self.chunks if c.type_id == type_id]

    def has_type(self, type_id: int) -> bool:
        return any(c.type_id == type_id for c in self.chunks)


# ── Specific Parsers ─────────────────────────────────────

# Language order for HZD LocalizedTextResource extra data
HZD_LANGUAGES = [
    'en',       # English = 0 (index 0)
    'fr',       # French
    'es',       # Spanish
    'de',       # German
    'it',       # Italian
    'nl',       # Dutch
    'pt',       # Portuguese
    'zh-Hant',  # Chinese Traditional
    'ko',       # Korean
    'ru',       # Russian
    'pl',       # Polish
    'da',       # Danish
    'fi',       # Finnish
    'no',       # Norwegian
    'sv',       # Swedish
    'ja',       # Japanese
    'es-419',   # LATAM Spanish
    'pt-BR',    # LATAM Portuguese
    'tr',       # Turkish
    'ar',       # Arabic
    'zh-Hans',  # Chinese Simplified
]

HZD_LANG_COUNT = 21


@dataclass
class LocalizedText:
    """Parsed LocalizedTextResource from a .core chunk."""
    chunk: CoreChunk
    strings: list[str]  # index by language position (0=English, etc.)

    @classmethod
    def parse(cls, chunk: CoreChunk) -> Optional['LocalizedText']:
        """Parse language strings from LocalizedTextResource extra data.

        The extra data at the end of the chunk contains:
            For each of 21 languages:
                uint16 string_length
                utf-8 text (string_length bytes)

        We scan backwards from the end to find the string data.
        """
        data = chunk.data
        if len(data) < 21 * 2:
            return None

        # The extra data is at the end. Parse from back to front.
        # First, find the start of the language data by trying to parse.
        # We know there are exactly 21 language entries.
        # Each entry: UInt16 length + UTF-8 text (length bytes)

        def try_parse_at(start_pos: int) -> Optional[list[str]]:
            strings = []
            pos = start_pos
            for _ in range(HZD_LANG_COUNT):
                if pos + 2 > len(data):
                    return None
                length = struct.unpack_from('<H', data, pos)[0]
                pos += 2
                if length == 0:
                    strings.append('')
                    continue
                if pos + length > len(data):
                    return None
                try:
                    text = data[pos:pos + length].decode('utf-8')
                except UnicodeDecodeError:
                    return None
                strings.append(text)
                pos += length
            return strings

        # Try multiple start positions, scanning from likely RTTI field boundaries.
        # The RTTI fields before extra data are small (no reflected members on
        # LocalizedTextResource itself, only inherited ones). The extra data
        # starts after ResourceWithoutLegacyName's fields.
        # We try positions from byte 8 through min(2000, len(data)-100)
        for start in range(8, min(2000, len(data) - 100), 4):
            strings = try_parse_at(start)
            if strings is not None:
                # Verify: strings should not all be empty
                if any(s for s in strings):
                    return cls(chunk=chunk, strings=strings)

        return None

    def get_text(self, lang_index: int) -> str:
        if 0 <= lang_index < len(self.strings):
            return self.strings[lang_index]
        return ''

    def set_text(self, lang_index: int, text: str) -> None:
        while len(self.strings) <= lang_index:
            self.strings.append('')
        self.strings[lang_index] = text

    def rebuild_data(self) -> bytes:
        """Rebuild the chunk data with modified language strings.

        We need to find where the extra data starts in the original chunk
        and replace it with updated strings.
        """
        data = bytearray(self.chunk.data)

        # Find the current extra data start by searching for the string pattern
        extra_start = None
        for start in range(8, min(2000, len(data) - 100), 4):
            pos = start
            valid = True
            for _ in range(HZD_LANG_COUNT):
                if pos + 2 > len(data):
                    valid = False
                    break
                length = struct.unpack_from('<H', data, pos)[0]
                pos += 2 + length
                if pos > len(data):
                    valid = False
                    break
            if valid and pos == len(data):
                extra_start = start
                break

        if extra_start is None:
            raise ValueError("Cannot find language string data in chunk")

        # Build new extra data
        new_extra = bytearray()
        for s in self.strings:
            encoded = s.encode('utf-8')
            new_extra.extend(struct.pack('<H', len(encoded)))
            new_extra.extend(encoded)

        # Replace from extra_start to end
        result = bytes(data[:extra_start]) + bytes(new_extra)
        return result

    def apply_to_chunk(self) -> None:
        """Write modified strings back to the chunk data."""
        self.chunk.data = self.rebuild_data()


@dataclass
class ParsedTexture:
    """Parsed HwTexture from a Texture/UITexture core chunk."""
    chunk: CoreChunk
    width: int
    height: int
    mip_count: int
    pixel_format: int
    texture_type: int
    embedded_data: bytes
    format_name: str = ''

    # Pixel format mapping (subset)
    FORMAT_NAMES = {
        0: 'RGBA_5551', 2: 'RGBA_4444', 8: 'RGB_565',
        12: 'RGBA_8888', 15: 'RGBA_FLOAT_32', 16: 'RGB_FLOAT_32',
        19: 'RGBA_FLOAT_16', 66: 'BC1', 67: 'BC2', 68: 'BC3',
        69: 'BC4U', 71: 'BC5U', 73: 'BC6U', 75: 'BC7',
    }

    BC_FORMATS = {66, 67, 68, 69, 71, 73, 75}

    @classmethod
    def parse(cls, chunk: CoreChunk, chunk_type: str = 'texture') -> Optional['ParsedTexture']:
        """Parse HwTexture data from a Texture or UITexture chunk.

        For Texture chunks, the HwTexture is in the extra data at the end.
        For UITexture, there are two HwTextures (low-res + high-res).

        HwTexture header (32 bytes):
            0: texture_type (uint8, 0=2D)
            2-3: width (uint16)
            4-5: height (uint16)
            6-7: slice_info (uint16)
            8: mip_count (uint8)
            9: pixel_format (uint8)
            ...
            Then: containerSize(uint32), embeddedDataSize(uint32),
                  streamedDataSize(uint32), streamedMipCount(uint32)
        """
        data = chunk.data
        if len(data) < 48:
            return None

        if chunk_type == 'uitexture':
            # UITexture has LowResDataSize + HiResDataSize before the HwTexture
            low_res_size = struct.unpack_from('<I', data, 0)[0]
            tex_start = 4
            if low_res_size == 0:
                # Try with offset 8
                tex_start = 8
        else:
            # Texture: find HwTexture by scanning for valid header
            tex_start = cls._find_hwtexture(data)

        if tex_start is None or tex_start + 32 > len(data):
            return None

        return cls._parse_hwtexture(chunk, data, tex_start)

    @classmethod
    def _find_hwtexture(cls, data: bytes) -> Optional[int]:
        """Find HwTexture header start in Texture extra data."""
        # Texture extra data starts at the end of RTTI fields.
        # RTTI fields for Resource: Name (BaseString) at some offset.
        # We scan for the HwTexture signature: texture_type in 0-3,
        # reasonable width/height (power-of-2 or common resolutions)
        for offset in range(4, min(200, len(data) - 48), 4):
            if cls._is_valid_tex_header(data, offset):
                return offset
        return None

    @classmethod
    def _is_valid_tex_header(cls, data: bytes, offset: int) -> bool:
        if offset + 48 > len(data):
            return False
        tex_type = data[offset]
        if tex_type > 3:  # 2D, 3D, CubeMap, 2DArray
            return False
        width = struct.unpack_from('<H', data, offset + 2)[0]
        height = struct.unpack_from('<H', data, offset + 4)[0]
        if width == 0 or height == 0 or width > 16384 or height > 16384:
            return False
        fmt = data[offset + 9]
        if fmt > 100:
            return False
        return True

    @classmethod
    def _parse_hwtexture(cls, chunk: CoreChunk, data: bytes,
                         offset: int) -> Optional['ParsedTexture']:
        tex_type = data[offset]
        width = struct.unpack_from('<H', data, offset + 2)[0]
        height = struct.unpack_from('<H', data, offset + 4)[0]
        mip_count = data[offset + 8]
        pixel_format = data[offset + 9]

        fmt_name = cls.FORMAT_NAMES.get(pixel_format, f'unknown_{pixel_format}')

        # Read container sizes at offset + 32
        container_size = struct.unpack_from('<I', data, offset + 32)[0]
        embedded_size = struct.unpack_from('<I', data, offset + 36)[0]
        streamed_size = struct.unpack_from('<I', data, offset + 40)[0]

        # Embedded data starts after the size fields and optional stream handle
        data_start = offset + 44  # after ContainerSize + EmbeddedDataSize + StreamedDataSize + StreamedMipCount
        if streamed_size > 0:
            # Skip stream handle: uint32 pathLen + UTF8 path + uint64 resourceOffset + uint64 resourceLength
            path_len = struct.unpack_from('<I', data, data_start)[0]
            data_start += 4 + path_len + 8 + 8

        # Embedded data from data_start to end of chunk
        # (container_size includes the header, so actual pixel data =
        #  container_size - header_and_handle_size)
        embedded_data = data[data_start:] if data_start < len(data) else b''

        return cls(
            chunk=chunk,
            width=width,
            height=height,
            mip_count=mip_count,
            pixel_format=pixel_format,
            texture_type=tex_type,
            embedded_data=embedded_data,
            format_name=fmt_name,
        )

    def build_dds_header(self) -> bytes:
        """Build a minimal DDS header for the texture data."""
        is_bc = self.pixel_format in self.BC_FORMATS
        fourcc = 0
        if self.pixel_format == 66:  # BC1
            fourcc = 0x31545844  # 'DXT1'
        elif self.pixel_format == 68:  # BC3
            fourcc = 0x33545844  # 'DXT3'
        elif self.pixel_format == 69:  # BC4
            fourcc = 0x34545844  # 'DXT4' (ATI1)
            fourcc = 0x31495441  # 'ATI1'
        elif self.pixel_format == 71:  # BC5
            fourcc = 0x32495441  # 'ATI2'
        elif self.pixel_format == 75:  # BC7
            fourcc = 0x44584237  # 'DX10' - needs DX10 extension header

        flags = 0x00081007  # CAPS | HEIGHT | WIDTH | PIXELFORMAT
        pf_flags = 0x0004 if is_bc else 0x0041  # FOURCC or RGB

        if self.pixel_format == 75:  # BC7 needs DX10
            pf_flags = 0x0004
            fourcc = 0x30315844  # 'DX10'

        header = bytearray(128)
        struct.pack_into('<I', header, 0, 0x20534444)   # Magic 'DDS '
        struct.pack_into('<I', header, 4, 124)           # Size
        struct.pack_into('<I', header, 8, flags)
        struct.pack_into('<I', header, 12, self.height)
        struct.pack_into('<I', header, 16, self.width)
        struct.pack_into('<I', header, 20, 0)            # PitchOrLinearSize
        struct.pack_into('<I', header, 28, self.mip_count)
        struct.pack_into('<I', header, 76, 32)           # PixelFormat size
        struct.pack_into('<I', header, 80, pf_flags)
        struct.pack_into('<I', header, 84, fourcc)
        struct.pack_into('<I', header, 108, 0x00401008)  # Caps

        return bytes(header)

    def to_dds(self) -> bytes:
        """Convert to DDS file bytes."""
        dds = bytearray()
        dds.extend(self.build_dds_header())
        dds.extend(self.embedded_data)
        return bytes(dds)


# ── Prefetch Parser ──────────────────────────────────────

@dataclass
class PrefetchList:
    """Parsed PrefetchList from fullgame.prefetch.core."""
    files: list[str]
    sizes: list[int]
    links: list[int]

    @classmethod
    def parse(cls, chunk: CoreChunk) -> Optional['PrefetchList']:
        """Parse PrefetchList from chunk data.

        PrefetchList RTTI fields:
            Files: Array<AssetPath>  — each AssetPath has Path: String
            Sizes: Array<int32>
            Links: Array<int32>      — flattened adjacency list

        We use a heuristic parser since we don't have full RTTI.
        """
        data = chunk.data
        if len(data) < 16:
            return None

        def read_string_at(pos: int) -> Optional[tuple[str, int]]:
            """Read a BaseString at pos, return (value, next_pos)."""
            if pos + 4 > len(data):
                return None
            length = struct.unpack_from('<I', data, pos)[0]
            if length == 0:
                return ('', pos + 4)
            if pos + 8 + length > len(data):
                return None
            try:
                value = data[pos + 8:pos + 8 + length].decode('utf-8')
            except UnicodeDecodeError:
                return None
            return (value, pos + 8 + length)

        # Try to read array of strings by scanning from beginning
        # Array header: count(uint32) + items
        num_files = struct.unpack_from('<I', data, 0)[0]
        if num_files == 0 or num_files > 500000:
            return None

        files = []
        pos = 4
        # Each AssetPath: Path (BaseString). Try reading N strings.
        for _ in range(num_files):
            result = read_string_at(pos)
            if result is None:
                break
            value, pos = result
            files.append(value)

        if len(files) != num_files:
            # Files array didn't parse cleanly; try alternate layout
            return None

        # Next: Sizes array (int32 count + items)
        if pos + 4 > len(data):
            return None
        num_sizes = struct.unpack_from('<I', data, pos)[0]
        pos += 4
        sizes = []
        for _ in range(num_sizes):
            if pos + 4 > len(data):
                break
            sizes.append(struct.unpack_from('<i', data, pos)[0])
            pos += 4

        # Next: Links array (int32 count + items)
        if pos + 4 > len(data):
            return cls(files=files, sizes=sizes, links=[])
        num_links = struct.unpack_from('<I', data, pos)[0]
        pos += 4
        links = []
        for _ in range(num_links):
            if pos + 4 > len(data):
                break
            links.append(struct.unpack_from('<i', data, pos)[0])
            pos += 4

        return cls(files=files, sizes=sizes, links=links)
