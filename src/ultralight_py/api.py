"""Python ownership and convenience layer over the native host adapter."""

from __future__ import annotations

import atexit
import traceback
import weakref
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from typing_extensions import Self

from ultralight_py import _asyncio, _native, _objects, _support, _waiting
from ultralight_py.input import InputView
from ultralight_py.objects import PythonBinding

if TYPE_CHECKING:
    from ultralight_py.images import RGBAImage

UltralightError = _native.UltralightError
JavaScriptError = _native.JavaScriptError
ErrorCode = _native.ErrorCode
Resource = _native.Resource
FrameEvent = _native.FrameEvent
LoadFailure = _native.LoadFailure
PageLoadError = _waiting.PageLoadError
undefined = _native.undefined


def _report(error: UltralightError) -> None:
    _native._report_unraisable(error)


def _callable(value, name: str) -> None:
    if value is not None and not callable(value):
        raise TypeError(f"{name} must be callable or None")


def _dimension(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("View dimensions must be integers")
    if not 0 < value <= 0xFFFFFFFF:
        raise ValueError("View dimensions must be positive uint32 values")
    return value


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


class Runtime:
    """One main-thread Renderer per process, shared until permanently closed."""

    _instance: Runtime | None = None

    def __new__(cls, *, assets_root=None, resource_loader=None, cache_path=None):
        _support.ensure_in_main_thread()
        _callable(resource_loader, "resource_loader")
        resolved_cache = None if cache_path is None else Path(cache_path).resolve()
        if resolved_cache is not None and "\0" in str(resolved_cache):
            raise ValueError("Runtime cache_path cannot contain NUL")
        current = cls._instance
        if current is not None:
            if current.closed:
                raise _native._make_error(
                    ErrorCode.Closed, "Runtime was closed; Renderer recreation is unsupported"
                )
            if assets_root is not None and Path(assets_root).resolve() != current._assets_root:
                raise ValueError("Runtime assets_root is already configured")
            if resource_loader is not None and resource_loader is not current._resource_loader:
                raise ValueError("Runtime resource_loader is already configured")
            if cache_path is not None and resolved_cache != current._cache_path:
                raise ValueError("Runtime cache_path is already configured")
            return current
        self = super().__new__(cls)
        self._assets_root = Path.cwd() if assets_root is None else Path(assets_root).resolve()
        self._resource_loader = resource_loader
        self._cache_path = resolved_cache
        self._views = weakref.WeakSet()
        self._updating = False
        self._error_handler = _report
        self._native = _support.call(
            _native._Runtime.create,
            str(self._assets_root),
            resource_loader,
            "" if resolved_cache is None else str(resolved_cache),
        )
        self._native.set_error_handler(_report)
        cls._instance = self
        return self

    @property
    def closed(self) -> bool:
        return self._native.closed

    def create_view(self, width: int, height: int, *, transparent: bool = False) -> View:
        return View(
            _support.call(
                self._native.create_view, _dimension(width), _dimension(height), transparent
            ),
            self,
        )

    def update(self) -> None:
        _support.ensure_in_main_thread()
        if self._updating:
            raise _native._make_error(ErrorCode.Busy, "Runtime.update cannot be re-entered")
        self._updating = True
        try:
            _asyncio.flush(self)
            _support.call(self._native.update)
            for view in tuple(self._views):
                view._state.notify(poll=True)
        finally:
            self._updating = False

    def refresh_display(self, display_id: int = 0) -> None:
        _support.call(self._native.refresh_display, display_id)

    def render(self) -> None:
        _support.call(self._native.render)

    def set_error_handler(self, callback: Callable | None) -> None:
        _callable(callback, "callback")
        _support.call(self._native.set_error_handler, _report if callback is None else callback)
        self._error_handler = _report if callback is None else callback

    def _report_callback_error(self, error):
        reported = _native._make_error(ErrorCode.HostException, str(error))
        reported.stack = "".join(
            traceback.format_exception(type(error), error, error.__traceback__)
        )
        try:
            self._error_handler(reported)
        except Exception as handler_error:  # noqa: BLE001 — isolate error-handler failures
            _native._report_unraisable(handler_error)

    def close(self) -> None:
        try:
            _support.call(self._native.close)
        finally:
            if self.closed:
                for view in tuple(self._views):
                    view._state.close()
                _asyncio.stop(self, _native._make_error(ErrorCode.Closed, "Runtime closed"))
                driver = getattr(self, "_async_driver", None)
                if driver is not None:
                    driver.close()
                script_driver = getattr(self, "_script_driver", None)
                if script_driver is not None:
                    script_driver.close()
                self._resource_loader = None
                self._error_handler = _report

    def __enter__(self) -> Self:
        _support.ensure_in_main_thread()
        if self.closed:
            raise _native._make_error(ErrorCode.Closed, "Runtime is closed")
        return self

    def __exit__(self, *exc) -> None:
        self.close()


class View(InputView):
    """An offscreen page. Use close() or a context manager for prompt release."""

    def __init__(self, native, runtime=None):
        self._native = native
        self._runtime = Runtime._instance if runtime is None else runtime
        self._state = _waiting.PageState(self, self._runtime)
        self._runtime._views.add(self)
        state = weakref.ref(self._state)

        def forward(name):
            def emit(event):
                current = state()
                if current is not None:
                    current.emit(name, event)

            return emit

        _support.call(native.set_callbacks, {name: forward(name) for name in _waiting.EVENTS})

    @property
    def closed(self) -> bool:
        return self._native.closed

    def load_html(self, html: str, url: str = "") -> None:
        if not isinstance(html, str) or not isinstance(url, str):
            raise TypeError("html and url must be strings")
        self._load(self._native.load_html, html, url)

    def load_url(self, url: str) -> None:
        if not isinstance(url, str):
            raise TypeError("url must be a string")
        self._load(self._native.load_url, url)

    def _load(self, function, *args):
        self._state.start_load()
        try:
            _support.call(function, *args)
        except Exception as error:
            for waiter in tuple(self._state.waiters):
                if not waiter.future.done():
                    waiter.future.set_exception(error)
            raise

    @property
    def is_ready(self) -> bool:
        self._state.check_open()
        return self._state.ready

    @property
    def is_settled(self) -> bool:
        self._state.check_open()
        return self._state.settled and not self._state.pending_begin

    @property
    def navigation_id(self) -> int:
        self._state.check_open()
        return self._state.navigation_id

    @property
    def load_failure(self):
        self._state.check_open()
        return self._state.load_failure

    def on(self, event, callback):
        return self._state.subscribe(event, callback)

    async def wait_ready(self, timeout=5) -> None:
        await self._state.wait(lambda: self._state.ready, timeout, events=True)

    async def wait_settled(self, timeout=5) -> None:
        await self._state.wait(lambda: self._state.settled, timeout, events=True)

    async def wait_until(self, predicate, timeout=5):
        return await self._state.wait(predicate, timeout)

    async def wait_for_selector(self, selector, timeout=5) -> bool:
        expression = _waiting.selector_expression(selector)
        return await self.wait_until(
            lambda: self._state.ready and self.evaluate(expression), timeout
        )

    def resize(self, width: int, height: int) -> None:
        _support.call(self._native.resize, _dimension(width), _dimension(height))

    def set_callbacks(
        self,
        *,
        begin_loading=None,
        window_ready=None,
        dom_ready=None,
        finish_loading=None,
        fail_loading=None,
        console=None,
        page_settled=None,
    ) -> None:
        callbacks = {
            "begin_loading": begin_loading,
            "window_ready": window_ready,
            "dom_ready": dom_ready,
            "finish_loading": finish_loading,
            "fail_loading": fail_loading,
            "console": console,
            "page_settled": page_settled,
        }
        for name, callback in callbacks.items():
            _callable(callback, name)
        self._state.check_open()
        self._state.callbacks = callbacks

    def evaluate_handle(self, source: str) -> JSValue:
        return JSValue(_support.call(self._native.evaluate_handle, source))

    def evaluate(self, source: str):
        with self.evaluate_handle(source) as value:
            return value.to_python()

    async def evaluate_async(self, source: str):
        with self.evaluate_handle(source) as value:
            if _support.call(value._native.is_promise):
                with await value.await_result() as result:
                    return result.to_python()
            return value.to_python()

    def bind_object(
        self, name: str, instance: object, *, members: Sequence[str] | None = None
    ) -> PythonBinding:
        if not isinstance(name, str):
            raise TypeError("Binding name must be str")
        if members is not None:
            if isinstance(members, str):
                raise TypeError("members must be a sequence of public names")
            members = tuple(members)
            if any(not isinstance(member, str) or member.startswith("_") for member in members):
                raise ValueError("members must contain public names")
            if set(members) - set(_objects.members(instance)):
                raise ValueError("members contains an unknown Python member")
        return PythonBinding(_support.call(self._native.bind_object, name, instance, members))

    def unbind(self, name: str) -> None:
        if not isinstance(name, str):
            raise TypeError("Binding name must be str")
        _support.call(self._native.unbind, name)

    def bind_function(self, name: str, callback: Callable) -> PythonBinding:
        if not callable(callback):
            raise TypeError("callback must be callable")
        return self.bind_object(name, callback)

    def copy_pixels(self) -> PixelBuffer:
        return PixelBuffer(**_support.call(self._native.copy_pixels))

    def clear_dirty_bounds(self) -> None:
        _support.call(self._native.clear_dirty_bounds)

    def close(self) -> None:
        try:
            _support.call(self._native.close)
        finally:
            if self.closed:
                self._state.close()

    def __enter__(self) -> Self:
        _support.ensure_in_main_thread()
        if self.closed:
            raise _native._make_error(ErrorCode.Closed, "View is closed")
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def __del__(self):
        native = getattr(self, "_native", None)
        if native is not None and not native.closed:
            native._defer_close()


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
            raise _native._make_error(ErrorCode.PageGone, "JSValue is closed")
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def _shutdown() -> None:
    runtime = Runtime._instance
    if runtime is not None:
        runtime.close()
    _native._drain()


atexit.register(_shutdown)
