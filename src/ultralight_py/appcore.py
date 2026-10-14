"""Native AppCore windows sharing the Python Runtime and asyncio loop."""

from __future__ import annotations

import asyncio
import inspect
import math
import weakref
from pathlib import Path

from typing_extensions import Self

from ultralight_py import _asyncio, _native, _support
from ultralight_py import api as _api
from ultralight_py.events import Subscription


def dimension(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("Window dimensions must be numbers")
    if not math.isfinite(value) or value <= 0:
        raise ValueError("Window dimensions must be finite and positive")
    return value


def text(value, name):
    if not isinstance(value, str):
        raise TypeError(f"{name} must be str")
    if "\0" in value:
        raise ValueError(f"{name} cannot contain NUL")
    return value


class Window:
    """One native window and its root View; dimensions are logical pixels."""

    def __init__(self, native, application, view, title):
        self._native = native
        self._application = application
        self.view = view
        self._title = title
        # Subscription shares the same state protocol as page subscriptions.
        self.subscriptions = {"closed": {}, "resized": {}}
        self._closed = False
        weak = weakref.ref(self)

        def emit(event, value):
            current = weak()
            if current is not None:
                current._emit(event, value)

        _support.call(native.set_callback, emit)

    @property
    def closed(self):
        return self._closed or self._native.closed

    def check_open(self):
        _support.call(self._native.check)

    @property
    def width(self):
        return _support.call(lambda: self._native.width)

    @property
    def height(self):
        return _support.call(lambda: self._native.height)

    @property
    def device_width(self):
        return _support.call(lambda: self._native.device_width)

    @property
    def device_height(self):
        return _support.call(lambda: self._native.device_height)

    @property
    def device_scale(self):
        return _support.call(lambda: self._native.device_scale)

    @property
    def title(self):
        self.check_open()
        return self._title

    @title.setter
    def title(self, value):
        _support.call(self._native.set_title, text(value, "title"))
        self._title = value

    def on(self, event, callback):
        self.check_open()
        if event not in self.subscriptions:
            raise ValueError(f"Unknown Window event: {event!r}")
        if not callable(callback):
            raise TypeError("callback must be callable")
        subscription = Subscription(self, event, callback)
        self.subscriptions[event][subscription] = None
        return subscription

    def _emit(self, event, value):
        if self._closed:
            return
        if event == "closed":
            self._closed = True
            self.view._state.close()
            self._application._windows.discard(self)
            if not self._application._windows:
                self._application.close()
        for subscription in tuple(self.subscriptions[event]):
            if subscription.closed:
                continue
            try:
                result = subscription._callback(value)
                if inspect.isawaitable(result):
                    if inspect.iscoroutine(result):
                        result.close()
                    raise TypeError("Window event callbacks must be synchronous")
            except Exception as error:  # noqa: BLE001 — isolate window subscribers
                self._application.runtime._report_callback_error(error)
        if event == "closed":
            for subscriptions in self.subscriptions.values():
                for subscription in tuple(subscriptions):
                    subscription.close()

    def close(self):
        _support.call(self._native.close)

    def __enter__(self) -> Self:
        self.check_open()
        return self

    def __exit__(self, *exc):
        self.close()


class Application:
    """Create before Runtime; the last window closes the application permanently."""

    def __init__(
        self,
        *,
        assets_root=None,
        resource_loader=None,
        cache_path=None,
        app_name="ultralight-py",
        developer_name="ultralight-py",
        force_cpu_renderer=False,
    ):
        _support.ensure_in_main_thread()
        if _api.Runtime._instance is not None:
            raise _native._make_error(
                _native.ErrorCode.InvalidArgument, "Create Application before Runtime"
            )
        _api._callable(resource_loader, "resource_loader")
        _api._bool(force_cpu_renderer, "force_cpu_renderer")
        assets = Path.cwd() if assets_root is None else Path(assets_root).resolve()
        cache = None if cache_path is None else Path(cache_path).resolve()
        text(str(assets), "assets_root")
        if cache is not None:
            text(str(cache), "cache_path")
        self._windows = set()
        self._closed = False
        self._closing = False
        self._stepping = False
        self._running = False
        self._tick_waiters = set()
        self._wake = None
        self._native = _support.call(
            _native._Application.create,
            str(assets),
            resource_loader,
            "" if cache is None else str(cache),
            text(app_name, "app_name"),
            text(developer_name, "developer_name"),
            force_cpu_renderer,
        )
        runtime = object.__new__(_api.Runtime)
        runtime._assets_root = assets
        runtime._cache_path = cache
        runtime._resource_loader = resource_loader
        runtime._views = weakref.WeakSet()
        runtime._sessions = {}
        runtime._updating = False
        runtime._error_handler = _api._report
        runtime._native = self._native.runtime
        runtime._application = self
        runtime._native.set_error_handler(_api._report)
        self.runtime = runtime
        _api.Runtime._instance = runtime

    @property
    def closed(self):
        return self._closed or self.runtime.closed

    def create_window(
        self,
        width,
        height,
        *,
        title="",
        session=None,
        view=None,
        transparent=False,
        resizable=True,
        fullscreen=False,
    ):
        _support.ensure_in_main_thread()
        dimension(width)
        dimension(height)
        text(title, "title")
        for name, value in (
            ("transparent", transparent),
            ("resizable", resizable),
            ("fullscreen", fullscreen),
        ):
            _api._bool(value, name)
        if view is not None:
            if not isinstance(view, _api.View):
                raise TypeError("view must be View or None")
            if view._runtime is not self.runtime:
                raise _native._make_error(
                    _native.ErrorCode.CrossContext, "View belongs to another Runtime"
                )
            if session is not None:
                raise ValueError("An adopted View already has a Session")
        if session is not None:
            if not isinstance(session, _api.Session):
                raise TypeError("session must be Session or None")
            if session._runtime is not self.runtime:
                raise _native._make_error(
                    _native.ErrorCode.CrossContext, "Session belongs to another Runtime"
                )
        native = _support.call(
            self._native.create_window,
            width,
            height,
            title,
            None if session is None else session._native,
            None if view is None else view._native,
            transparent,
            resizable,
            fullscreen,
        )
        if view is None:
            view = _api.View(native.view, self.runtime, session)
        window = Window(native, self, view, title)
        self._windows.add(window)
        return window

    def _advance(self):
        if self._stepping:
            raise _native._make_error(
                _native.ErrorCode.Busy, "Application step cannot be re-entered"
            )
        self._stepping = True
        try:
            _asyncio.flush(self.runtime)
            running = _support.call(self._native.run_once)
            for view in tuple(self.runtime._views):
                if view.closed:
                    view._state.close()
                else:
                    view._state.notify(poll=True)
            for waiter in tuple(self._tick_waiters):
                if not waiter.done():
                    waiter.set_result(None)
            if not running:
                self.close()
            return running and not self.closed
        finally:
            self._stepping = False

    def run_once(self):
        """Step AppCore; an external asyncio host must advance its own event loop."""
        _support.ensure_in_main_thread()
        if self._running:
            raise _native._make_error(_native.ErrorCode.Busy, "Application is already being driven")
        if self.closed:
            return False
        return self._advance()

    async def _next_tick(self, *, render=False):
        if not self._running or self.closed:
            raise _native._make_error(_native.ErrorCode.Closed, "Application loop is not running")
        loop = _asyncio.associate(self.runtime)
        waiter = loop.create_future()
        self._tick_waiters.add(waiter)
        try:
            await waiter
        finally:
            self._tick_waiters.discard(waiter)

    async def run_async(self, update_interval=1 / 60):
        _support.ensure_in_main_thread()
        if isinstance(update_interval, bool) or not isinstance(update_interval, (float, int)):
            raise TypeError("update_interval must be a number")
        if not math.isfinite(update_interval) or update_interval <= 0:
            raise ValueError("update_interval must be finite and positive")
        if self._running or self._stepping:
            raise _native._make_error(_native.ErrorCode.Busy, "Application is already being driven")
        if self.closed:
            return
        _asyncio.associate(self.runtime)
        self._wake = asyncio.Event()
        self._running = True
        try:
            while not self.closed and self._advance():
                try:
                    await asyncio.wait_for(self._wake.wait(), update_interval)
                except asyncio.TimeoutError:
                    pass
        finally:
            self._running = False
            self.close()
            # Let bridge cancellation and pending wait callbacks run before returning.
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            self._wake = None

    def run(self):
        _support.ensure_in_main_thread()
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.run_async())
        raise RuntimeError("Use await app.run_async() inside an asyncio loop")

    def _finish_close(self):
        if self._closed:
            return
        self._closed = True
        error = _native._make_error(_native.ErrorCode.Closed, "Application closed")
        for waiter in tuple(self._tick_waiters):
            if not waiter.done():
                waiter.set_exception(error)
        if self._wake is not None:
            self._wake.set()
        self._windows.clear()

    def close(self):
        _support.ensure_in_main_thread()
        if self._closing or self._closed:
            return
        self._closing = True
        try:
            _support.call(self._native.close)
        finally:
            if self.runtime.closed:
                self.runtime._finish_close()
                self._finish_close()
            self._closing = False

    def __enter__(self) -> Self:
        _support.call(self._native.check)
        return self

    def __exit__(self, *exc):
        self.close()
