"""Passive page observation. No operation in this module pumps the engine."""

from __future__ import annotations

import asyncio
import inspect
import json
import math
import weakref

from ultralight_py import _asyncio, _native, _support
from ultralight_py.events import Subscription

EVENTS = (
    "begin_loading",
    "window_ready",
    "dom_ready",
    "finish_loading",
    "fail_loading",
    "console",
    "page_settled",
)


class PageLoadError(RuntimeError):
    """A main-frame loading failure, retaining the SDK's structured details."""

    def __init__(self, failure):
        self.failure = failure
        super().__init__(
            f"Page load failed: {failure.description} ({failure.domain}:{failure.code})"
        )


def validate_timeout(timeout, name="timeout"):
    valid = isinstance(timeout, (int, float)) and not isinstance(timeout, bool)
    try:
        valid = valid and math.isfinite(timeout) and timeout > 0
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError(f"{name} must be a positive finite number")


def selector_expression(selector):
    if not isinstance(selector, str) or not selector:
        raise ValueError("selector must be a nonempty string")
    return f"!!document.querySelector({json.dumps(selector)})"


def check_predicate(predicate):
    value = predicate()
    if inspect.isawaitable(value):
        if inspect.iscoroutine(value):
            value.close()
        raise TypeError("wait_until requires a synchronous predicate; use evaluate_async")
    return value


class _Waiter:
    def __init__(self, state, future, predicate, events):
        self.state = state
        self.future = future
        self.predicate = predicate
        self.events = events
        self.navigation = state.navigation_id
        self.request = None

    def validate(self):
        state = self.state
        if state.closed:
            raise _native._make_error(_native.ErrorCode.Closed, "View is closed")
        if self.request is None:
            if self.navigation != state.navigation_id:
                raise _native._make_error(_native.ErrorCode.PageGone, "Page changed while waiting")
        elif state.request_id != self.request:
            raise _native._make_error(_native.ErrorCode.PageGone, "Navigation was superseded")
        if state.load_failure is not None:
            raise PageLoadError(state.load_failure)
        return True

    def check(self, poll=False):
        if self.future.done():
            return
        try:
            if not self.validate():
                return
            if self.events or poll:
                value = check_predicate(self.predicate)
                if value and not self.future.done():
                    self.future.set_result(value)
        except Exception as error:  # noqa: BLE001 — deliver predicate failures to their waiter
            if not self.future.done():
                self.future.set_exception(error)


class _NavigationWaiter(_Waiter):
    def __init__(self, *args):
        super().__init__(*args)
        self.request = self.state.request_id
        self.started = False

    def validate(self):
        if self.state.closed:
            raise _native._make_error(_native.ErrorCode.Closed, "View is closed")
        if not self.started:
            if self.navigation == self.state.navigation_id:
                return False
            self.started = True
            self.request = self.state.request_id
        return super().validate()


class _PendingWait:
    """Register synchronously, then await with one deadline and deterministic cleanup."""

    def __init__(self, state, predicate, timeout, *, events=False, navigation=False):
        validate_timeout(timeout)
        state.check_open()
        self.state = state
        self.loop = _asyncio.associate(state.runtime)
        self.deadline = self.loop.time() + timeout
        waiter_type = _NavigationWaiter if navigation else _Waiter
        self.waiter = waiter_type(state, self.loop.create_future(), predicate, events)
        self.closed = False
        state.waiters.add(self.waiter)
        state.runtime._async_work.add(self.stop)
        self.waiter.check(poll=True)

    def stop(self, error):
        if not self.waiter.future.done():
            self.waiter.future.set_exception(error)

    async def result(self):
        waiter = self.waiter
        try:
            while True:
                future = waiter.future
                if future.done():
                    value = future.result()
                else:
                    try:
                        value = await asyncio.wait_for(
                            future, max(0, self.deadline - self.loop.time())
                        )
                    except asyncio.TimeoutError:
                        if future.cancelled():
                            raise TimeoutError("Page wait timed out") from None
                        raise
                if waiter.validate() and (not waiter.events or waiter.predicate()):
                    return value
                # An engine navigation chain may start again before this task resumes.
                waiter.future = self.loop.create_future()
        finally:
            self.close()

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.state.waiters.discard(self.waiter)
        self.state.runtime._async_work.discard(self.stop)
        future = self.waiter.future
        if not future.done():
            future.cancel()
        elif not future.cancelled():
            future.exception()


class PageState:
    def __init__(self, view, runtime):
        self.view = weakref.ref(view)
        self.runtime = runtime
        self.navigation_id = 0
        self.request_id = 0
        self.pending_begin = False
        self.ready = False
        self.settled = False
        self.load_failure = None
        self.closed = False
        self.callbacks = {}
        self.subscriptions = {name: {} for name in EVENTS}
        self.waiters = set()

    def check_open(self):
        view = self.view()
        if self.closed or view is None:
            _support.ensure_in_main_thread()
            raise _native._make_error(_native.ErrorCode.Closed, "View is closed")
        _support.call(view._native._check)

    def reset(self):
        self.navigation_id += 1
        self.ready = self.settled = False
        self.load_failure = None

    def start_load(self):
        self.check_open()
        self.request_id += 1
        self.pending_begin = True
        self.reset()
        self.notify()

    def notify(self, poll=False):
        for waiter in tuple(self.waiters):
            waiter.check(poll)

    def emit(self, name, event):
        if self.closed:
            return
        callback = self.callbacks.get(name)
        subscribers = tuple(self.subscriptions[name])
        main = (
            event.frame.is_main_frame
            if name == "fail_loading"
            else getattr(event, "is_main_frame", False)
        )
        if name == "begin_loading" and main:
            if not self.pending_begin:
                self.reset()
            self.pending_begin = False
        elif name == "dom_ready" and main and not self.pending_begin:
            self.ready = self.load_failure is None
        elif name == "fail_loading" and main:
            self.load_failure = event
            self.ready = self.settled = False
        elif name == "page_settled" and self.ready and not self.pending_begin:
            self.settled = self.load_failure is None
        self.notify()
        if callback is not None:
            self.invoke(callback, event)
        for subscription in subscribers:
            if self.closed:
                break
            if not subscription.closed:
                self.invoke(subscription._callback, event)

    def invoke(self, callback, event):
        try:
            result = callback(event)
            if inspect.isawaitable(result):
                if inspect.iscoroutine(result):
                    result.close()
                raise TypeError("View event callbacks must be synchronous")
        except Exception as error:  # noqa: BLE001 — isolate subscribers individually
            self.runtime._report_callback_error(error)

    def subscribe(self, event, callback):
        self.check_open()
        if event not in EVENTS:
            raise ValueError(f"Unknown View event: {event!r}")
        if not callable(callback):
            raise TypeError("callback must be callable")
        subscription = Subscription(self, event, callback)
        self.subscriptions[event][subscription] = None
        return subscription

    def close(self):
        self.closed = True
        self.ready = self.settled = False
        self.callbacks.clear()
        for subscriptions in self.subscriptions.values():
            for subscription in tuple(subscriptions):
                subscription.close()
        self.notify()

    def expect_navigation(self, wait_until, timeout):
        if wait_until not in ("ready", "settled"):
            raise ValueError("wait_until must be 'ready' or 'settled'")
        return _PendingWait(
            self, lambda: getattr(self, wait_until), timeout, events=True, navigation=True
        )

    async def wait(self, predicate, timeout, *, events=False):
        pending = _PendingWait(self, predicate, timeout, events=events)
        try:
            return await pending.result()
        finally:
            pending.close()
