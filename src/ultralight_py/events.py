"""Closeable, synchronous View event subscriptions."""

from __future__ import annotations

import weakref

from ultralight_py import _support


class Subscription:
    """Retained by the View until explicitly closed or the View closes."""

    def __init__(self, state, event, callback):
        self._state = weakref.ref(state)
        self._event = event
        self._callback = callback

    @property
    def closed(self) -> bool:
        return self._callback is None

    def close(self) -> None:
        _support.ensure_in_main_thread()
        state = self._state()
        if state is not None:
            if not state.closed:
                state.check_open()
            state.subscriptions[self._event].pop(self, None)
        self._callback = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
