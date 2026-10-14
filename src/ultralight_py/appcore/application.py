"""AppCore application and event-loop driver."""

from __future__ import annotations

import asyncio
import math
import weakref
from pathlib import Path

from typing_extensions import Self

import ultralight_py.api._shared as _api_shared
from ultralight_py import _asyncio, _lifecycle, _native, _support
from ultralight_py import api as _api
from ultralight_py.appcore import _shared
from ultralight_py.appcore.window import Window


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
        _api_shared.validate_callable(resource_loader, "resource_loader")
        _api_shared.validate_bool(force_cpu_renderer, "force_cpu_renderer")
        assets = Path.cwd() if assets_root is None else Path(assets_root).resolve()
        cache = None if cache_path is None else Path(cache_path).resolve()
        _shared.text(str(assets), "assets_root")
        if cache is not None:
            _shared.text(str(cache), "cache_path")
        self._windows = set()
        self._closed = False
        self._closing = False
        self._stepping = False
        self._running = False
        self._tick_waiters = set()
        self._wake = None
        _lifecycle.register_shutdown()
        self._native = _support.call(
            _native._Application.create,
            str(assets),
            resource_loader,
            "" if cache is None else str(cache),
            _shared.text(app_name, "app_name"),
            _shared.text(developer_name, "developer_name"),
            force_cpu_renderer,
        )
        runtime = object.__new__(_api.Runtime)
        runtime._assets_root = assets
        runtime._cache_path = cache
        runtime._resource_loader = resource_loader
        runtime._views = weakref.WeakSet()
        runtime._sessions = {}
        runtime._updating = False
        runtime._error_handler = _api_shared.report_error
        runtime._native = self._native.runtime
        runtime._application = self
        runtime._native.set_error_handler(_api_shared.report_error)
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
        _shared.dimension(width)
        _shared.dimension(height)
        _shared.text(title, "title")
        for name, value in (
            ("transparent", transparent),
            ("resizable", resizable),
            ("fullscreen", fullscreen),
        ):
            _api_shared.validate_bool(value, name)
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
