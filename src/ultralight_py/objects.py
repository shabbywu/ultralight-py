"""Document-local ownership of exported Python bindings."""

from __future__ import annotations

from typing_extensions import Self

from ultralight_py import _support


class PythonBinding:
    """A document-local binding; close it to revoke all proxies it exported."""

    def __init__(self, native):
        self._native = native

    @property
    def closed(self) -> bool:
        return self._native.closed

    def close(self) -> None:
        _support.call(self._native.close)

    def __enter__(self) -> Self:
        _support.call(self._native.check)
        return self

    def __exit__(self, *exc) -> None:
        self.close()
