"""Font texture extraction from Decima archives.

Font textures are stored in Texture and UITexture .core files.
They use BCn (block compression) formats:
- BC4/BC5 on PS4 (ATI 3Dc variant)
- BC7 on PC

This module extracts raw texture data and wraps it with a DDS header
for viewing/editing in standard tools.

Based on research from:
  - HzDTextureExplorer (https://github.com/torandi/HzDTextureExplorer)
  - ProjectDecima (https://github.com/torandi/ProjectDecima)
  - HZDCoreEditor (https://github.com/Nukem9/HZDCoreE)

Credit:
  - Decima-Explorer (https://github.com/acrinym/Decima-Explorer) — HwTexture format
  - decima-workshop (https://github.com/ShadelessFox/decima-workshop) — type IDs
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .archive import DecimaArchive
from .core import (
    CoreFile,
    ParsedTexture,
    TYPE_TEXTURE,
    TYPE_UI_TEXTURE,
    TYPE_TEXTURE_LIST,
)


@dataclass
class FontInfo:
    """Metadata about an extracted font texture."""
    hash_val: int
    file_path: str
    width: int
    height: int
    pixel_format: int
    format_name: str
    data_size: int
    output_path: str = ''


def extract_from_archive(archive_path: str | Path,
                         output_dir: str | Path,
                         file_names: Optional[dict[int, str]] = None,
                         extract_all: bool = False
                         ) -> list[FontInfo]:
    """Extract texture files from an archive.

    Args:
        archive_path: Path to .bin archive
        output_dir: Directory to save .dds files
        file_names: Optional hash→path mapping
        extract_all: If True, extract ALL textures, not just font-named ones

    Returns:
        List of FontInfo for extracted textures
    """
    archive = DecimaArchive.open(archive_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    fonts = []

    for file_entry in archive.file_entries:
        path_str = ''
        if file_names and file_entry.hash in file_names:
            path_str = file_names[file_entry.hash]
            if not extract_all:
                is_font = any(kw in path_str.lower() for kw in
                              ('font', 'glyph', 'typeface', 'type_face'))
                if not is_font:
                    continue

        try:
            data = archive.extract(file_entry)
        except Exception:
            continue

        try:
            core = CoreFile.read(data)
        except Exception:
            continue

        for chunk_type, tag in [(TYPE_TEXTURE, 'texture'),
                                 (TYPE_UI_TEXTURE, 'uitexture'),
                                 (TYPE_TEXTURE_LIST, 'texturelist')]:
            chunks = core.find_chunks(chunk_type)
            for chunk in chunks:
                tex = ParsedTexture.parse(chunk, chunk_type=tag)
                if tex is None or not tex.embedded_data:
                    continue

                dds_data = tex.to_dds()

                if path_str:
                    safe_name = path_str.replace('/', '_').replace('\\', '_')
                else:
                    safe_name = f'{file_entry.hash:016x}'

                filename = f'{safe_name}_{tex.width}x{tex.height}_{tex.format_name}.dds'
                filepath = output_dir / filename
                filepath.write_bytes(dds_data)

                fonts.append(FontInfo(
                    hash_val=file_entry.hash,
                    file_path=path_str,
                    width=tex.width,
                    height=tex.height,
                    pixel_format=tex.pixel_format,
                    format_name=tex.format_name,
                    data_size=len(tex.embedded_data),
                    output_path=str(filepath),
                ))

    return fonts
