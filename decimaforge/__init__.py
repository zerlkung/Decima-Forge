"""DecimaForge — Decima Engine Archive Toolkit.

A Python toolkit for extracting, modifying, and repacking game archives
from Decima Engine games (Horizon Zero Dawn, Death Stranding).

Provides:
- Archive (.bin) parsing, extraction, and repacking
- Localization text export/import (LocalizedTextResource)
- Font texture extraction (HwTexture → DDS)
- Prefetch file list extraction
- MurmurHash3_x64_128 path hashing

Credit:
  - Decima-Explorer (https://github.com/acrinym/Decima-Explorer)
  - decima-workshop (https://github.com/ShadelessFox/decima-workshop)
  - HZDCoreEditor (https://github.com/Nukem9/HZDCoreE)
  - smhasher (https://github.com/aappleby/smhasher) — MurmurHash3 reference
"""

__version__ = '0.2.0'
__all__ = [
    'DecimaArchive',
    'CoreFile',
    'LocalizedText',
    'OodleKraken',
    'hash_path',
    'extract_to_json',
    'import_from_json',
    'extract_fonts',
    'extract_prefetch_to_file',
]
