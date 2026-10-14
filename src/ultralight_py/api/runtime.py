"""Runtime and storage session ownership."""

from __future__ import annotations

import traceback
import weakref
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from typing_extensions import Self

from ultralight_py import _asyncio, _lifecycle, _native, _support
from ultralight_py.api import _shared

if TYPE_CHECKING:
    from ultralight_py.api.view import View


class Session:
    """Browser storage shared by Views in one Runtime."""

    def __init__(self, native, runtime, name, persistent):
        self._native = native
        self._runtime = runtime
        self._name = name
        self._persistent = persistent
        self._disk_path = Path(native.disk_path).resolve() if persistent else None

    @property
    def name(self) -> str:
        return self._name

    @property
    def persistent(self) -> bool:
        return self._persistent

    @property
    def disk_path(self) -> Path | None:
        return self._disk_path

    @property
    def closed(self) -> bool:
        return self._native.closed

    def close(self, *, force_close: bool = False) -> None:
        _shared.validate_bool(force_close, "force_close")
        try:
            _support.call(self._native.close, force_close)
        finally:
            if self.closed:
                for view in tuple(self._runtime._views):
                    if view.session is self and view.closed:
                        view._state.close()
                if self._runtime._sessions.get(self.name) is self:
                    del self._runtime._sessions[self.name]

    def __enter__(self) -> Self:
        _support.call(self._native.check)
        return self

    def __exit__(self, *exc) -> None:
        self.close()


class Runtime:
    """One main-thread Renderer per process, shared until permanently closed."""

    _instance: Runtime | None = None

    def __new__(cls, *, assets_root=None, resource_loader=None, cache_path=None):
        _support.ensure_in_main_thread()
        _shared.validate_callable(resource_loader, "resource_loader")
        resolved_cache = None if cache_path is None else Path(cache_path).resolve()
        if resolved_cache is not None and "\0" in str(resolved_cache):
            raise ValueError("Runtime cache_path cannot contain NUL")
        current = cls._instance
        if current is not None:
            if current.closed:
                raise _native._make_error(
                    _native.ErrorCode.Closed,
                    "Runtime was closed; Renderer recreation is unsupported",
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
        self._sessions = {}
        self._updating = False
        self._error_handler = _shared.report_error
        _lifecycle.register_shutdown()
        self._native = _support.call(
            _native._Runtime.create,
            str(self._assets_root),
            resource_loader,
            "" if resolved_cache is None else str(resolved_cache),
        )
        self._native.set_error_handler(_shared.report_error)
        cls._instance = self
        return self

    @property
    def closed(self) -> bool:
        return self._native.closed

    def create_session(self, name: str, *, persistent: bool = False) -> Session:
        _shared.validate_session_name(name)
        _shared.validate_bool(persistent, "persistent")
        native = _support.call(self._native.create_session, name, persistent)
        session = Session(native, self, name, persistent)
        self._sessions[name] = session
        return session

    def get_session(self, name: str) -> Session | None:
        _shared.validate_session_name(name)
        _support.call(self._native.check)
        return self._sessions.get(name)

    def get_or_create_session(self, name: str, *, persistent: bool = False) -> Session:
        _shared.validate_bool(persistent, "persistent")
        session = self.get_session(name)
        if session is not None:
            if session.persistent != persistent:
                raise ValueError("Session persistence is already configured")
            return session
        return self.create_session(name, persistent=persistent)

    def create_view(
        self,
        width: int,
        height: int,
        *,
        transparent: bool = False,
        session: Session | None = None,
    ) -> View:
        from ultralight_py.api.view import View

        if session is not None:
            if not isinstance(session, Session):
                raise TypeError("session must be Session or None")
            if session._runtime is not self:
                raise _native._make_error(
                    _native.ErrorCode.CrossContext, "Session belongs to another Runtime"
                )
        return View(
            _support.call(
                self._native.create_view,
                _shared.validate_dimension(width),
                _shared.validate_dimension(height),
                transparent,
                None if session is None else session._native,
            ),
            self,
            session,
        )

    def update(self) -> None:
        _support.ensure_in_main_thread()
        if self.closed:
            raise _native._make_error(_native.ErrorCode.Closed, "Runtime is closed")
        if getattr(self, "_application", None) is not None:
            raise _native._make_error(_native.ErrorCode.Unsupported, "AppCore drives this Runtime")
        if self._updating:
            raise _native._make_error(_native.ErrorCode.Busy, "Runtime.update cannot be re-entered")
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
        _shared.validate_callable(callback, "callback")
        _support.call(
            self._native.set_error_handler,
            _shared.report_error if callback is None else callback,
        )
        self._error_handler = _shared.report_error if callback is None else callback

    def _report_callback_error(self, error):
        reported = _native._make_error(_native.ErrorCode.HostException, str(error))
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
                self._finish_close()

    def _finish_close(self):
        if getattr(self, "_python_closed", False):
            return
        self._python_closed = True
        for view in tuple(self._views):
            view._state.close()
        _asyncio.stop(self, _native._make_error(_native.ErrorCode.Closed, "Runtime closed"))
        driver = getattr(self, "_async_driver", None)
        if driver is not None:
            driver.close()
        script_driver = getattr(self, "_script_driver", None)
        if script_driver is not None:
            script_driver.close()
        self._sessions.clear()
        self._resource_loader = None
        self._error_handler = _shared.report_error
        application = getattr(self, "_application", None)
        if application is not None:
            application._finish_close()

    def __enter__(self) -> Self:
        _support.ensure_in_main_thread()
        if self.closed:
            raise _native._make_error(_native.ErrorCode.Closed, "Runtime is closed")
        return self

    def __exit__(self, *exc) -> None:
        self.close()
