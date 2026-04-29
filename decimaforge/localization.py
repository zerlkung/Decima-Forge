"""Localization text extraction and import for Decima archives.

Localized text is stored in LocalizedTextResource objects within .core files
inside .bin archives. This module:

1. Finds .core files containing LocalizedTextResource chunks
2. Extracts language strings to JSON
3. Imports modified strings back, preserving binary structure

HZD Language order (21 languages):
    en, fr, es, de, it, nl, pt, zh-Hant, ko, ru, pl,
    da, fi, no, sv, ja, es-419, pt-BR, tr, ar, zh-Hans

PUA (Private Use Area) characters:
    Decima uses U+E000–U+F8FF as inline text markup (section separators,
    font size/color changes, glyph references). During export, these are
    converted to readable tags like {F1A1}. During import, tags are
    converted back to PUA characters.

Credit:
  - HZDCoreEditor (https://github.com/Nukem9/HZDCoreE) — LocalizedTextResource format, language order
  - decima-workshop (https://github.com/ShadelessFox/decima-workshop) — PUA character handling
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .archive import DecimaArchive
from .core import (
    CoreFile,
    CoreChunk,
    LocalizedText,
    TYPE_LOCALIZED_TEXT,
    HZD_LANGUAGES,
)

# ── PUA ↔ Tag conversion ─────────────────────────────────

_PUA_TAG_RE = re.compile(r'\{([0-9A-Fa-f]{4})\}')


def pua_to_tags(text: str) -> str:
    """Convert PUA characters to readable tags.

    U+F1A1 → {F1A1}
    """
    def _replace(c):
        cp = ord(c)
        if 0xE000 <= cp <= 0xF8FF:
            return f'{{{cp:04X}}}'
        return c
    return ''.join(_replace(c) for c in text)


def tags_to_pua(text: str) -> str:
    """Convert tags back to PUA characters.

    {F1A1} → U+F1A1
    """

    def _restore(m):
        cp = int(m.group(1), 16)
        return chr(cp)
    return _PUA_TAG_RE.sub(_restore, text)


@dataclass
class LocEntry:
    """A single localization entry (one .core file's text in all languages)."""
    file_hash: int
    file_path: str = ''
    strings: dict[str, str] = field(default_factory=dict)  # lang_code → text

    @property
    def has_text(self) -> bool:
        return any(v for v in self.strings.values())


def extract_from_archive(archive_path: str | Path,
                         file_names: Optional[dict[int, str]] = None
                         ) -> list[LocEntry]:
    """Extract all localization entries from an archive.

    Args:
        archive_path: Path to .bin archive
        file_names: Optional hash→path mapping for naming entries

    Returns:
        List of LocEntry with text in all 21 languages
    """
    archive = DecimaArchive.open(archive_path)
    entries = []

    for file_entry in archive.file_entries:
        try:
            data = archive.extract(file_entry)
        except Exception:
            continue

        try:
            core = CoreFile.read(data)
        except Exception:
            continue

        loc_chunks = core.find_chunks(TYPE_LOCALIZED_TEXT)
        if not loc_chunks:
            continue

        for chunk in loc_chunks:
            loc_text = LocalizedText.parse(chunk)
            if loc_text is None:
                continue

            entry = LocEntry(file_hash=file_entry.hash)
            if file_names and file_entry.hash in file_names:
                entry.file_path = file_names[file_entry.hash]

            for i, lang in enumerate(HZD_LANGUAGES):
                text = loc_text.get_text(i)
                if text:
                    entry.strings[lang] = pua_to_tags(text)

            entries.append(entry)
            break  # one LocEntry per .core file

    return entries


def extract_to_json(archive_path: str | Path,
                    output_path: str | Path,
                    file_names: Optional[dict[int, str]] = None,
                    target_lang: Optional[str] = None) -> dict:
    """Extract localization to a JSON file.

    Args:
        archive_path: Path to .bin archive
        output_path: Output JSON file path
        file_names: Optional hash→path mapping
        target_lang: Optional language code to filter (e.g., 'th').

    Returns:
        JSON-serializable dict
    """
    entries = extract_from_archive(archive_path, file_names)

    result = {
        'game': 'Horizon Zero Dawn',
        'languages': HZD_LANGUAGES,
        'entry_count': len(entries),
        'entries': [],
    }

    for entry in entries:
        name = entry.file_path or f'{entry.file_hash:016x}'
        item = {'id': name, 'hash': entry.file_hash}
        if target_lang:
            item['source'] = entry.strings.get('en', '')
            item['target'] = entry.strings.get(target_lang, '')
        else:
            item['strings'] = entry.strings
        result['entries'].append(item)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding='utf-8',
    )

    return result


def import_from_json(archive_path: str | Path,
                     json_path: str | Path,
                     output_dir: str | Path,
                     target_lang: str) -> dict:
    """Import modified translations from JSON into .core files.

    Reads the JSON file, finds matching .core files in the archive,
    modifies the target language strings, and writes modified .core files
    to the output directory.

    Args:
        archive_path: Path to original .bin archive
        json_path: Path to JSON file with translations
        output_dir: Directory to write modified .core files

    Returns:
        Stats dict with counts
    """
    json_data = json.loads(Path(json_path).read_text(encoding='utf-8'))
    archive = DecimaArchive.open(archive_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Build language index
    try:
        lang_idx = HZD_LANGUAGES.index(target_lang)
    except ValueError:
        raise ValueError(f"Unknown language: {target_lang}. Known: {HZD_LANGUAGES}")

    # Build hash → target text mapping from JSON
    translations: dict[int, str] = {}
    for item in json_data.get('entries', []):
        hash_val = item.get('hash', 0)
        target = item.get('target', '')
        if hash_val and target:
            translations[hash_val] = target

    stats = {'found': 0, 'modified': 0, 'written': 0}

    for file_entry in archive.file_entries:
        if file_entry.hash not in translations:
            continue
        stats['found'] += 1

        try:
            data = archive.extract(file_entry)
        except Exception:
            continue

        try:
            core = CoreFile.read(data)
        except Exception:
            continue

        loc_chunks = core.find_chunks(TYPE_LOCALIZED_TEXT)
        if not loc_chunks:
            continue

        for chunk in loc_chunks:
            loc_text = LocalizedText.parse(chunk)
            if loc_text is None:
                continue

            new_text = translations[file_entry.hash]
            # Convert tags back to PUA characters
            new_text = tags_to_pua(new_text)
            loc_text.set_text(lang_idx, new_text)
            loc_text.apply_to_chunk()
            stats['modified'] += 1
            break

        # Write modified .core file
        filename = f'{file_entry.hash:016x}.core'
        filepath = output_dir / filename
        filepath.write_bytes(core.write())
        stats['written'] += 1

    return stats
