"""Command-line interface for DecimaForge.

Credit:
  - Decima-Explorer (https://github.com/acrinym/Decima-Explorer)
  - decima-workshop (https://github.com/ShadelessFox/decima-workshop)
  - HZDCoreEditor (https://github.com/Nukem9/HZDCoreE)
"""

import argparse
import sys
from pathlib import Path

from .archive import DecimaArchive
from .localization import extract_to_json, import_from_json, HZD_LANGUAGES
from .font import extract_from_archive as extract_fonts
from .prefetch import (
    extract_paths,
    extract_paths_cached,
    build_global_hash_map,
)
from .hash import hash_path


def _resolve_names(target_archive, prefetch_archive=None):
    """Build hash→path map, optionally using a separate prefetch source."""
    archives = [prefetch_archive, target_archive] if prefetch_archive else [target_archive]
    return build_global_hash_map(archives)


def cmd_list(args):
    archive = DecimaArchive.open(args.archive)
    print(f"Archive: {args.archive}")
    print(f"  Magic: {archive.magic:#010x} ({'encrypted' if archive.is_encrypted else 'plain'})")
    print(f"  File size: {archive.file_size:,}")
    print(f"  Data size: {archive.data_size:,}")
    print(f"  Files: {archive.file_count}")
    print(f"  Chunks: {archive.chunk_count}")
    print(f"  Max chunk: {archive.max_chunk_size:#x}")
    print()

    if archive.file_count <= 50 or args.all:
        limit = archive.file_count
    else:
        limit = 50

    print(f"File table (showing {limit}/{archive.file_count}):")
    print(f"{'Index':>6}  {'Hash':>18}  {'Offset':>12}  {'Size':>12}")
    print("-" * 56)
    for entry in archive.file_entries[:limit]:
        print(f"{entry.index:>6}  {entry.hash:#018x}  {entry.offset:#010x}  {entry.size:#010x}")

    if archive.file_count > 50 and not args.all:
        print(f"  ... and {archive.file_count - 50} more files")


def cmd_extract(args):
    archive = DecimaArchive.open(args.archive)

    if args.file.startswith('0x'):
        hash_val = int(args.file, 16)
        entry = archive.find_file(hash_val)
    else:
        entry = archive.find_file_by_path(args.file)

    if entry is None:
        print(f"File not found: {args.file}", file=sys.stderr)
        return 1

    data = archive.extract(entry)
    output = args.output or f'{entry.hash:016x}'
    Path(output).write_bytes(data)
    print(f"Extracted {len(data):,} bytes to {output}")
    return 0


def cmd_unpack(args):
    archive = DecimaArchive.open(args.archive)

    file_names = None
    if not args.no_names:
        try:
            file_names = _resolve_names(args.archive, args.prefetch)
            print(f"Loaded {len(file_names)} file names from prefetch")
        except Exception as e:
            print(f"Note: Could not load file names: {e}")

    output_dir = args.output or (Path(args.archive).stem + '_extracted')
    manifest = archive.unpack_all(output_dir, file_names)
    print(f"Unpacked {manifest['file_count']} files to {output_dir}")
    return 0


def cmd_repack(args):
    from .compression import get_oodle

    manifest_path = Path(args.folder) / 'manifest.json'
    if not manifest_path.exists():
        print(f"manifest.json not found in {args.folder}", file=sys.stderr)
        return 1

    import json
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))

    files = []
    for finfo in manifest['files']:
        filepath = Path(args.folder) / finfo['filename']
        if not filepath.exists():
            print(f"File missing: {filepath}", file=sys.stderr)
            return 1
        files.append((finfo['hash'], filepath.read_bytes()))

    output = args.output or 'repacked.bin'
    oodle = get_oodle()
    archive = DecimaArchive.build(files, output, oodle)
    print(f"Repacked {len(files)} files to {output} ({archive.file_size:,} bytes)")
    return 0


def cmd_export_loc(args):
    file_names = None
    if not args.no_names:
        try:
            file_names = _resolve_names(args.archive, args.prefetch)
        except Exception:
            pass

    output = args.output or 'localization.json'
    result = extract_to_json(args.archive, output, file_names, args.lang)
    count = len(result['entries'])
    print(f"Exported {count} localization entries to {output}")
    return 0


def cmd_import_loc(args):
    output_dir = args.output or 'localization_imported'
    stats = import_from_json(args.archive, args.json_file, output_dir, args.lang)
    print(f"Found {stats['found']} matching files")
    print(f"Modified {stats['modified']} text entries")
    print(f"Wrote {stats['written']} .core files to {output_dir}")
    return 0


def cmd_extract_fonts(_args):
    file_names = None
    try:
        file_names = _resolve_names(_args.archive, _args.prefetch)
    except Exception:
        pass

    output_dir = _args.output or (Path(_args.archive).stem + '_fonts')
    results = extract_fonts(_args.archive, output_dir, file_names)
    print(f"Extracted {len(results)} font textures to {output_dir}")
    for font in results:
        print(f"  {font.width}x{font.height} {font.format_name} "
              f"({font.data_size:,} bytes) → {Path(font.output_path).name}")
    return 0


def cmd_hash(_args):
    h = hash_path(_args.path)
    print(f"{_args.path}  →  {h:#018x}")
    return 0


def cmd_file_list(_args):
    target = DecimaArchive.open(_args.archive)
    output = _args.output or (Path(_args.archive).stem + '_file_list.txt')

    if _args.prefetch:
        paths = extract_paths_cached(_args.prefetch)
        target_hashes = {e.hash for e in target.file_entries}
        paths = [p for p in paths if any(
            hash_path(v) in target_hashes
            for v in (p, p + '.core', p + '.core.stream')
        )]
    else:
        paths = extract_paths(target)

    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text('\n'.join(paths), encoding='utf-8')
    print(f"Extracted {len(paths)} file paths to {output}")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description='DecimaForge — Decima Engine Archive Toolkit',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  decimaforge list initial.bin
  decimaforge extract initial.bin "models/characters/aloy/model.core"
  decimaforge unpack Patch_HZDTHAI.bin --prefetch initial.bin
  decimaforge export-loc initial_english.bin --lang th
  decimaforge import-loc initial_english.bin loc.json --lang th
  decimaforge extract-fonts initial.bin
  decimaforge file-list Patch_HZDTHAI.bin --prefetch initial.bin
  decimaforge hash "ui/fonts/font_book.core"
        """,
    )

    subs = parser.add_subparsers(dest='command')

    # list
    p = subs.add_parser('list', help='List files in archive')
    p.add_argument('archive')
    p.add_argument('--all', '-a', action='store_true', help='Show all files')
    p.set_defaults(func=cmd_list)

    # extract
    p = subs.add_parser('extract', help='Extract single file')
    p.add_argument('archive')
    p.add_argument('file', help='File hash (0x...) or path')
    p.add_argument('output', nargs='?', help='Output file')
    p.set_defaults(func=cmd_extract)

    # unpack
    p = subs.add_parser('unpack', help='Unpack entire archive')
    p.add_argument('archive')
    p.add_argument('output', nargs='?', help='Output directory')
    p.add_argument('--prefetch', help='Archive with prefetch data (e.g., initial.bin)')
    p.add_argument('--no-names', action='store_true', help='Do not resolve file names')
    p.set_defaults(func=cmd_unpack)

    # repack
    p = subs.add_parser('repack', help='Repack extracted folder to archive')
    p.add_argument('folder', help='Folder with manifest.json')
    p.add_argument('output', nargs='?', help='Output .bin file')
    p.set_defaults(func=cmd_repack)

    # export-loc
    p = subs.add_parser('export-loc', help='Export localization to JSON')
    p.add_argument('archive')
    p.add_argument('output', nargs='?', help='Output JSON file')
    p.add_argument('--lang', help='Target language code (e.g., th, fr, zh-Hant)')
    p.add_argument('--prefetch', help='Archive with prefetch data (e.g., initial.bin)')
    p.add_argument('--no-names', action='store_true', help='Do not resolve file names')
    p.set_defaults(func=cmd_export_loc)

    # import-loc
    p = subs.add_parser('import-loc', help='Import localization from JSON')
    p.add_argument('archive')
    p.add_argument('json_file')
    p.add_argument('output', nargs='?', help='Output directory')
    p.add_argument('--lang', required=True, help='Target language code')
    p.set_defaults(func=cmd_import_loc)

    # extract-fonts
    p = subs.add_parser('extract-fonts', help='Extract font textures')
    p.add_argument('archive')
    p.add_argument('output', nargs='?', help='Output directory')
    p.add_argument('--prefetch', help='Archive with prefetch data (e.g., initial.bin)')
    p.set_defaults(func=cmd_extract_fonts)

    # file-list
    p = subs.add_parser('file-list', help='Extract file path list from prefetch')
    p.add_argument('archive')
    p.add_argument('output', nargs='?', help='Output text file')
    p.add_argument('--prefetch', help='Archive with prefetch data (e.g., initial.bin)')
    p.set_defaults(func=cmd_file_list)

    # hash
    p = subs.add_parser('hash', help='Compute path hash')
    p.add_argument('path')
    p.set_defaults(func=cmd_hash)

    # Parse
    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        return 1

    return args.func(args) or 0


if __name__ == '__main__':
    sys.exit(main())
