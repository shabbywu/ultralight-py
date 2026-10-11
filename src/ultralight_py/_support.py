"""Shared main-thread entry and deferred native cleanup."""
import threading

from ultralight_py import _native


def ensure_in_main_thread() -> None:
    if threading.current_thread() is not threading.main_thread():
        raise _native._make_error(_native.ErrorCode.WrongThread,
                                  "Operation requires the Python main thread")


def call(function, *args, **kwargs):
    ensure_in_main_thread()
    try:
        return function(*args, **kwargs)
    finally:
        _native._drain()
