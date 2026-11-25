"""Windows-only compatibility patches for importing ansible 6.x locally.

Loaded automatically via PYTHONPATH; does not change the project source.
"""

import ctypes
import ctypes.util
import multiprocessing
import os

# ansible 6.x builds regexes from os.path.sep assuming POSIX separators.
os.path.sep = "/"

# Windows has no fork start method; use spawn for local import verification.
_original_get_context = multiprocessing.get_context


def _get_context(method=None):
    if method == "fork":
        method = "spawn"
    return _original_get_context(method)


multiprocessing.get_context = _get_context


class _FuncStub:
    argtypes = ()
    restype = None

    def __call__(self, *args, **kwargs):
        return 1


class _LibCStub:
    wcwidth = _FuncStub()
    wcswidth = _FuncStub()


_original_load_library = ctypes.cdll.LoadLibrary


def _load_library(name, *args, **kwargs):
    if not name:
        return _LibCStub()
    return _original_load_library(name, *args, **kwargs)


ctypes.cdll.LoadLibrary = _load_library
