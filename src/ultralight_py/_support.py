"""Shared main-thread entry and deferred native cleanup."""
import threading

from . import _native


def _main_thread() -> None:
    if threading.current_thread() is not threading.main_thread():
        raise _native._make_error(_native.ErrorCode.WrongThread,
                                  "Operation requires the Python main thread")


def _call(function, *args, **kwargs):
    _main_thread()
    try:
        return function(*args, **kwargs)
    finally:
        _native._drain()
