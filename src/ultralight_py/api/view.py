"""Offscreen View API."""

from __future__ import annotations

import weakref
from collections.abc import Callable, Sequence

from typing_extensions import Self

from ultralight_py import _native, _objects, _support, _waiting
from ultralight_py.api import _shared
from ultralight_py.api.runtime import Session
from ultralight_py.api.values import JSValue, PixelBuffer
from ultralight_py.input import InputView
from ultralight_py.objects import PythonBinding


class View(InputView):
    """An offscreen page. Use close() or a context manager for prompt release."""

    def __init__(self, native, runtime=None, session=None):
        if runtime is None:
            from ultralight_py.api.runtime import Runtime

        self._session = session
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

        def closed():
            current = state()
            if current is not None:
                current.close()

        _support.call(native.set_close_callback, closed)

    @property
    def closed(self) -> bool:
        return self._native.closed

    @property
    def session(self) -> Session | None:
        return self._session

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
        _support.call(
            self._native.resize,
            _shared.validate_dimension(width),
            _shared.validate_dimension(height),
        )

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
            _shared.validate_callable(callback, name)
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
            raise _native._make_error(_native.ErrorCode.Closed, "View is closed")
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def __del__(self):
        native = getattr(self, "_native", None)
        if native is not None and not native.closed:
            native._defer_close()
