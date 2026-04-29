"""Prefetch file list extraction for hash→path resolution.

Decima .bin archives store only 64-bit hashes, not file paths.
The path→hash mapping is stored in `prefetch/fullgame.prefetch.core`
inside the main archive (usually initial.bin).

The PrefetchList contains:
- Files: Array of file paths (e.g., "models/characters/aloy/core/model.core")
- Sizes: Array of decompressed file sizes
- Links: Flattened adjacency list of cross-file references

This module extracts the file list and builds a hash→path lookup table.

Credit:
  - decima-workshop (https://github.com/ShadelessFox/decima-workshop) — PrefetchList format, path variants
  - Decima-Explorer (https://github.com/acrinym/Decima-Explorer) — prefetch file discovery
"""

from pathlib import Path
from typing import Optional

from .archive import DecimaArchive
from .core import CoreFile, PrefetchList, TYPE_PREFETCH_LIST
from .hash import hash_path


def extract_paths(archive: DecimaArchive) -> list[str]:
    """Extract all file paths from a prefetch .core file in the archive.

    Looks for PrefetchList chunks and returns the file paths.
    """
    # Find the prefetch file by scanning for PrefetchList type
    for entry in archive.file_entries:
        try:
            data = archive.extract(entry)
        except Exception:
            continue

        try:
            core = CoreFile.read(data)
        except Exception:
            continue

        chunks = core.find_chunks(TYPE_PREFETCH_LIST)
        for chunk in chunks:
            prefetch = PrefetchList.parse(chunk)
            if prefetch and prefetch.files:
                return prefetch.files

    return []


def build_hash_map(archive: DecimaArchive) -> dict[int, str]:
    """Build a hash→path mapping from prefetch data.

    For each path in the prefetch list, computes the MurmurHash3 hash
    and checks if it exists in the archive. Also tries .core and
    .core.stream extensions.

    Returns:
        Dict mapping hash → path
    """
    paths = extract_paths(archive)
    if not paths:
        return {}

    # Build set of all hashes in this archive for fast lookup
    archive_hashes = {e.hash for e in archive.file_entries}

    hash_map: dict[int, str] = {}
    for path in paths:
        for variant in _path_variants(path):
            h = hash_path(variant)
            if h in archive_hashes:
                hash_map[h] = variant
                break

    return hash_map


def _path_variants(path: str) -> list[str]:
    """Generate candidate path variants for hash lookup."""
    variants = [path]
    if not path.endswith('.core'):
        variants.append(path + '.core')
    if not path.endswith('.core.stream'):
        variants.append(path + '.core.stream')
    return variants


def build_global_hash_map(archive_paths: list[str | Path]) -> dict[int, str]:
    """Build a hash→path mapping from multiple archives.

    Extracts prefetch data from the first archive that has it, then
    maps paths to hashes across all archives.

    Args:
        archive_paths: List of paths to .bin archives

    Returns:
        Dict mapping hash → path
    """
    all_paths = []

    # Collect all paths from all archives
    for ap in archive_paths:
        archive = DecimaArchive.open(ap)
        paths = extract_paths(archive)
        if paths:
            all_paths.extend(paths)
        # Use the first archive with prefetch data as source
        if all_paths:
            break

    if not all_paths:
        return {}

    # Build set of all hashes across all archives
    all_hashes: set[int] = set()
    for ap in archive_paths:
        try:
            archive = DecimaArchive.open(ap)
            all_hashes.update(e.hash for e in archive.file_entries)
        except Exception:
            continue

    # Map paths to hashes
    hash_map: dict[int, str] = {}
    for path in all_paths:
        for variant in _path_variants(path):
            h = hash_path(variant)
            if h in all_hashes:
                hash_map[h] = variant
                break

    return hash_map


def extract_prefetch_to_file(archive: DecimaArchive,
                              output: str | Path) -> list[str]:
    """Extract file path list from prefetch data to a text file.

    Args:
        archive: DecimaArchive to extract from
        output: Output text file path (one path per line)

    Returns:
        List of extracted paths
    """
    paths = extract_paths(archive)

    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text('\n'.join(paths), encoding='utf-8')

    return paths
