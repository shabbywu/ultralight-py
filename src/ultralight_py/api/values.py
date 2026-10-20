"""Owned values returned by the native API."""

from __future__ import annotations

from collections.abc import MutableMapping, MutableSequence
from dataclasses import dataclass
from operator import index
from reprlib import recursive_repr
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

    def to_python(self, *, copy: bool = False):
        return _support.call(self._native.to_python, copy=copy)

    def close(self) -> None:
        _support.call(self._native.close)

    def __enter__(self) -> Self:
        _support.ensure_in_main_thread()
        if self.closed:
            raise _native._make_error(_native.ErrorCode.PageGone, "JSValue is closed")
        return self

    def __exit__(self, *exc) -> None:
        self.close()


class _JSContainer:
    """Own a document-scoped handle independently of temporary JSValue handles."""

    def __init__(self, native):
        self._native = native

    @property
    def closed(self) -> bool:
        return self._native.closed

    def _operation(self, operation, *args):
        return _support.call(self._native.container, operation, *args)

    def to_python(self, *, copy: bool = False):
        return _support.call(self._native.to_python, copy=copy)

    def close(self) -> None:
        _support.call(self._native.close)

    def __enter__(self) -> Self:
        _support.ensure_in_main_thread()
        if self.closed:
            raise _native._make_error(_native.ErrorCode.PageGone, "JavaScript container is closed")
        return self

    def __exit__(self, *exc) -> None:
        self.close()


class JSArray(_JSContainer, MutableSequence):
    """A live JavaScript Array exposed as a Python mutable sequence."""

    def __len__(self):
        return self._operation("length")

    def _index(self, key):
        key = index(key)
        length = len(self)
        if key < 0:
            key += length
        if not 0 <= key < length:
            raise IndexError("JavaScript array index out of range")
        return key

    def __getitem__(self, key):
        if isinstance(key, slice):
            return [self[i] for i in range(*key.indices(len(self)))]
        return self._operation("get", self._index(key))

    def __setitem__(self, key, value):
        if isinstance(key, slice):
            start, stop, step = key.indices(len(self))
            values = list(value)
            if step == 1:
                self._operation("splice", start, max(0, stop - start), *values)
            else:
                indices = range(start, stop, step)
                if len(indices) != len(values):
                    raise ValueError("Extended slice assignment size mismatch")
                for i, item in zip(indices, values):
                    self._operation("set", i, item)
            return
        self._operation("set", self._index(key), value)

    def __delitem__(self, key):
        if isinstance(key, slice):
            start, stop, step = key.indices(len(self))
            if step == 1:
                self._operation("splice", start, max(0, stop - start))
            else:
                for i in sorted(range(start, stop, step), reverse=True):
                    self._operation("splice", i, 1)
        else:
            self._operation("splice", self._index(key), 1)

    def insert(self, position, value):
        position = index(position)
        length = len(self)
        position = max(0, position + length) if position < 0 else min(position, length)
        self._operation("splice", position, 0, value)

    def sort(self, *, key=None, reverse=False):
        values = sorted(self, key=key, reverse=reverse)
        self[:] = values

    def copy(self):
        return list(self)

    def __eq__(self, other):
        if self is other:
            return True
        if isinstance(other, (list, JSArray)):
            return list(self) == list(other)
        return NotImplemented

    @recursive_repr()
    def __repr__(self):
        return f"JSArray({list(self)!r})"


class JSObject(_JSContainer, MutableMapping):
    """A live JavaScript object's own enumerable string properties."""

    def _key(self, key):
        if not isinstance(key, str):
            raise TypeError("JavaScript object keys must be strings")
        return key

    def __iter__(self):
        return iter(_support.call(self._native.keys))

    def __len__(self):
        return len(_support.call(self._native.keys))

    def __getitem__(self, key):
        key = self._key(key)
        if key not in self:
            raise KeyError(key)
        return self._operation("get", key)

    def __setitem__(self, key, value):
        self._operation("set", self._key(key), value)

    def __delitem__(self, key):
        key = self._key(key)
        if key not in self:
            raise KeyError(key)
        self._operation("delete", key)

    def __contains__(self, key):
        return self._key(key) in _support.call(self._native.keys)

    def copy(self):
        return dict(self)

    @recursive_repr()
    def __repr__(self):
        return f"JSObject({dict(self)!r})"
