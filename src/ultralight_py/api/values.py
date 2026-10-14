"""Owned values returned by the native API."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from typing_extensions import Self

from ultralight_py import _asyncio, _native, _support

if TYPE_CHECKING:
    from ultralight_py.images import RGBAImage


@dataclass(frozen=True)
class PixelBuffer:
    width: int
    height: int
    row_bytes: int
    format: str
    dirty_bounds: tuple[int, int, int, int]
    data: bytes

    def to_rgba(self) -> RGBAImage:
        """Return an owned, tightly packed image with straight RGBA alpha."""
        from ultralight_py.images import to_rgba

        return to_rgba(self)


class JSValue:
    """A retained document-scoped JS value, invalid after navigation."""

    def __init__(self, native):
        self._native = native

    @property
    def closed(self) -> bool:
        return self._native.closed

    def get(self, key: str | int) -> JSValue:
        return JSValue(_support.call(self._native.get, key))

    def set(self, key: str | int, value) -> None:
        _support.call(self._native.set, key, value)

    def keys(self) -> list[str]:
        return _support.call(self._native.keys)

    def call(self, *args, this: JSValue | None = None) -> JSValue:
        return JSValue(_support.call(self._native.call, *args, this=this))

    async def await_result(self) -> JSValue:
        return await _asyncio.await_result(self)

    async def call_async(self, *args, this: JSValue | None = None) -> JSValue:
        result = self.call(*args, this=this)
        if _support.call(result._native.is_promise):
            try:
                return await result.await_result()
            finally:
                result.close()
        return result

    def to_python(self):
        return _support.call(self._native.to_python)

    def close(self) -> None:
        _support.call(self._native.close)

    def __enter__(self) -> Self:
        _support.ensure_in_main_thread()
        if self.closed:
            raise _native._make_error(_native.ErrorCode.PageGone, "JSValue is closed")
        return self

    def __exit__(self, *exc) -> None:
        self.close()
