"""Native window event and lifetime wrapper."""

from __future__ import annotations

import inspect
import weakref

from typing_extensions import Self

from ultralight_py import _support
from ultralight_py.appcore import _shared
from ultralight_py.events import Subscription


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
        _support.call(self._native.set_title, _shared.text(value, "title"))
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
