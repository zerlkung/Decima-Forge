"""Oodle Kraken compression/decompression via oo2core DLL.

Uses ctypes to call OodleLZ_Decompress and OodleLZ_Compress from the
RAD Game Tools Oodle library (oo2core_*_win64.dll).

Function signatures reverse-engineered from decima-workshop (Java FFM bindings)
and Decima-Explorer (C++ ooz fallback).

Credit:
  - decima-workshop (https://github.com/ShadelessFox/decima-workshop) — FFM bindings, function signatures
  - Decima-Explorer (https://github.com/acrinym/Decima-Explorer) — ooz fallback implementation
"""

import ctypes
import os
from pathlib import Path
from typing import Optional


class OodleError(Exception):
    """Failed to load Oodle DLL or decompress data."""
    pass


# Attempt to find the Oodle DLL
def _find_oodle_dll() -> Optional[Path]:
    """Search for oo2core DLL in common locations."""
    search_paths = [
        # Project root
        Path(__file__).parent.parent,
        # Game directories (common Steam/PS4 dump locations)
        Path(os.environ.get('DECIMA_GAME_DIR', '')),
        # Current working directory
        Path.cwd(),
    ]

    for version in range(9, -1, -1):
        dll_name = f'oo2core_{version}_win64.dll'
        for base in search_paths:
            if not base or not str(base):
                continue
            candidate = base / dll_name
            if candidate.exists():
                return candidate

    return None


class OodleKraken:
    """Oodle Kraken compressor via oo2core DLL."""

    def __init__(self, dll_path: Optional[str | Path] = None):
        if dll_path:
            self._dll_path = Path(dll_path)
        else:
            found = _find_oodle_dll()
            if found is None:
                raise OodleError(
                    "Oodle DLL not found. Place oo2core_7_win64.dll in the project root "
                    "or set DECIMA_GAME_DIR environment variable."
                )
            self._dll_path = found

        try:
            self._dll = ctypes.WinDLL(str(self._dll_path))
        except OSError as e:
            raise OodleError(f"Failed to load Oodle DLL: {self._dll_path}: {e}")

        self._decompress_fn = self._dll.OodleLZ_Decompress
        self._compress_fn = self._dll.OodleLZ_Compress

        # OodleLZ_Decompress signature (Windows x64 __fastcall)
        # Returns: int (decompressed size, 0 on failure)
        self._decompress_fn.argtypes = [
            ctypes.c_void_p,   # compBuf
            ctypes.c_size_t,   # compBufSize
            ctypes.c_void_p,   # rawBuf
            ctypes.c_size_t,   # rawLen
            ctypes.c_int,      # fuzzSafe (1)
            ctypes.c_int,      # checkCRC (1)
            ctypes.c_int,      # verbosity (0)
            ctypes.c_void_p,   # decBufBase (NULL)
            ctypes.c_size_t,   # decBufSize (0)
            ctypes.c_void_p,   # callback (NULL)
            ctypes.c_void_p,   # callbackCtx (NULL)
            ctypes.c_void_p,   # decoderMemory (NULL)
            ctypes.c_size_t,   # decoderMemorySize (0)
            ctypes.c_int,      # threadPhase (3)
        ]
        self._decompress_fn.restype = ctypes.c_size_t

        # OodleLZ_Compress signature
        # Returns: int (compressed size, 0 on failure)
        self._compress_fn.argtypes = [
            ctypes.c_int,      # codec (8=Kraken)
            ctypes.c_void_p,   # rawBuf
            ctypes.c_size_t,   # rawLen
            ctypes.c_void_p,   # compBuf
            ctypes.c_int,      # level (4=normal)
            ctypes.c_void_p,   # opts (NULL)
            ctypes.c_size_t,   # offs (0)
            ctypes.c_size_t,   # unused (0)
            ctypes.c_void_p,   # scratch (NULL)
            ctypes.c_size_t,   # scratchSize (0)
        ]
        self._compress_fn.restype = ctypes.c_size_t

    @property
    def dll_path(self) -> Path:
        return self._dll_path

    def decompress(self, data: bytes, uncompressed_size: int) -> bytes:
        """Decompress a Kraken-compressed buffer.

        Args:
            data: Compressed data
            uncompressed_size: Expected size after decompression

        Returns:
            Decompressed bytes

        Raises:
            OodleError: If decompression fails
        """
        src = ctypes.create_string_buffer(data, len(data))
        dst = ctypes.create_string_buffer(uncompressed_size)

        result = self._decompress_fn(
            src, len(data),
            dst, uncompressed_size,
            1, 1, 0,        # fuzzSafe, checkCRC, verbosity
            None, 0,         # decBufBase, decBufSize
            None, None,      # callback, callbackCtx
            None, 0,         # decoderMemory, decoderMemorySize
            3                # threadPhase
        )

        if result != uncompressed_size:
            raise OodleError(
                f"Decompression failed: expected {uncompressed_size} bytes, "
                f"got {result} bytes"
            )

        return bytes(dst)

    def compress(self, data: bytes, level: int = 4) -> bytes:
        """Compress data with Kraken.

        Args:
            data: Uncompressed data
            level: Compression level (0=none, 1=fast, 4=normal, 9=best)

        Returns:
            Compressed bytes
        """
        max_compressed = len(data) + 274 * ((len(data) + 0x3FFFF) // 0x40000)
        src = ctypes.create_string_buffer(data, len(data))
        dst = ctypes.create_string_buffer(max_compressed)

        result = self._compress_fn(
            8,               # codec = Kraken
            src, len(data),
            dst, level,
            None, 0, 0,      # opts, offs, unused
            None, 0,         # scratch, scratchSize
        )

        if result == 0:
            raise OodleError("Compression failed")

        return bytes(dst[:result])


_oodle: Optional[OodleKraken] = None


def get_oodle(dll_path: Optional[str | Path] = None) -> OodleKraken:
    """Get or create the global OodleKraken instance."""
    global _oodle
    if _oodle is None:
        _oodle = OodleKraken(dll_path)
    return _oodle
