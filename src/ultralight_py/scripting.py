"""Explicit, shared script driving over otherwise passive Views."""

from __future__ import annotations

import asyncio
import inspect

from ultralight_py import _asyncio, _native, _support, _waiting


class ScriptDriver:
    """Borrow a Runtime and ask a host to advance it, or explicitly use auto()."""

    def __init__(self, runtime, *, step=None):
        _support.ensure_in_main_thread()
        if step is None and getattr(runtime, "_application", None) is not None:
            step = runtime._application._next_tick
        if not callable(step):
            raise TypeError("step must be an async callable")
        if runtime.closed:
            raise _native._make_error(_native.ErrorCode.Closed, "Runtime is closed")
        if getattr(runtime, "_script_driver", None) is not None:
            raise RuntimeError("Runtime already has a script driver")
        self.runtime = runtime
        self.loop = _asyncio.associate(runtime)
        self.closed = False
        self.failure = self.loop.create_future()
        self._step = step
        self._automatic = False
        self._demands = {}
        self._pump_task = None
        self._cancelled_pumps = set()
        runtime._script_driver = self
        runtime._async_work.add(self.close)

    @classmethod
    def auto(cls, runtime, *, update_interval=1 / 60, display_id=0):
        """Create an on-demand main-thread pump; never close the borrowed Runtime."""
        _support.ensure_in_main_thread()
        if runtime.closed:
            raise _native._make_error(_native.ErrorCode.Closed, "Runtime is closed")
        if getattr(runtime, "_application", None) is not None:
            raise _native._make_error(_native.ErrorCode.Unsupported, "AppCore drives this Runtime")
        _waiting.validate_timeout(update_interval, "update_interval")
        if isinstance(display_id, bool) or not isinstance(display_id, int):
            raise TypeError("display_id must be an integer")
        if not 0 <= display_id <= 0xFFFFFFFF:
            raise ValueError("display_id must be a uint32")
        if getattr(runtime, "_async_driver", None) is not None:
            raise RuntimeError("Runtime already has an asyncio driver")
        previous = float("-inf")

        async def step(*, render=False):
            nonlocal previous
            loop = asyncio.get_running_loop()
            await asyncio.sleep(max(0, previous + update_interval - loop.time()))
            # asyncio timers can wake early on a coarse-resolution clock.
            while (remaining := previous + update_interval - loop.time()) > 0:
                await asyncio.sleep(remaining)
            # Waiters may have finished while this step was rate limited.
            active = [
                render for operation, render in driver._demands.items() if not operation.done()
            ]
            if not active:
                return
            previous = loop.time()
            runtime.update()
            runtime.refresh_display(display_id)
            if any(active):
                runtime.render()

        driver = cls(runtime, step=step)
        driver._automatic = True
        runtime._async_driver = driver
        return driver

    def _check(self):
        _support.ensure_in_main_thread()
        if self.failure.done():
            raise self.failure.result()
        if self.closed or self.runtime.closed:
            raise _native._make_error(_native.ErrorCode.Closed, "Script driver is closed")
        if asyncio.get_running_loop() is not self.loop:
            raise RuntimeError("Script driver belongs to another asyncio loop")
        _asyncio.associate(self.runtime)

    def page(self, view):
        self._check()
        if view._runtime is not self.runtime:
            raise ValueError("View belongs to another Runtime")
        view._state.check_open()
        return ScriptPage(self, view)

    def _ensure_pump(self):
        if self._pump_task is None:
            self._pump_task = self.loop.create_task(self._pump(), name="ultralight:script-pump")

    def _cancel_pump(self):
        task = self._pump_task
        if task is not None and task is not asyncio.current_task(loop=self.loop):
            self._cancelled_pumps.add(task)
            task.cancel()

    async def _pump(self):
        task = asyncio.current_task()
        try:
            while self._demands and not self.closed:
                active = [
                    render for operation, render in self._demands.items() if not operation.done()
                ]
                if not active:
                    break
                result = self._step(render=any(active))
                if not inspect.isawaitable(result):
                    raise TypeError("step must return an awaitable")
                await result
                # Let event waiters and Promise continuations finish before asking again.
                await asyncio.sleep(0)
        except asyncio.CancelledError as error:
            if task not in self._cancelled_pumps:
                self.close(error)
        except Exception as error:  # noqa: BLE001 — one pump failure reaches every operation
            self.close(error)
        finally:
            self._cancelled_pumps.discard(task)
            self._pump_task = None
            if not self.closed and any(not operation.done() for operation in self._demands):
                self._ensure_pump()

    async def _run(self, awaitable, *, timeout, render=False):
        operation = None
        try:
            self._check()
            _waiting.validate_timeout(timeout)
            if not isinstance(render, bool):
                raise TypeError("render must be bool")
            deadline = self.loop.time() + timeout
            operation = self.loop.create_task(awaitable)
            # Immediate results require no engine step.
            await asyncio.sleep(0)
            self._check()
            if operation.done():
                return operation.result()
            self._demands[operation] = render
            self._ensure_pump()
            done, _ = await asyncio.wait(
                (operation, self.failure),
                timeout=max(0, deadline - self.loop.time()),
                return_when=asyncio.FIRST_COMPLETED,
            )
            if self.failure in done:
                raise self.failure.result()
            if operation in done:
                return operation.result()
            raise TimeoutError("Script operation timed out")
        finally:
            if operation is None:
                awaitable.close()
            else:
                self._demands.pop(operation, None)
                if not operation.done():
                    operation.cancel()
                await asyncio.gather(operation, return_exceptions=True)
                if not self._demands:
                    self._cancel_pump()

    def close(self, error=None):
        _support.ensure_in_main_thread()
        if self.closed:
            return
        self.closed = True
        if not self.failure.done():
            self.failure.set_result(
                error or _native._make_error(_native.ErrorCode.Closed, "Script driver closed")
            )
        self._cancel_pump()
        self.runtime._async_work.discard(self.close)
        self.runtime._script_driver = None
        if self._automatic:
            self.runtime._async_driver = None

    async def __aenter__(self):
        self._check()
        return self

    async def __aexit__(self, *exc):
        self.close()
        pump = self._pump_task
        if pump is not None:
            await asyncio.gather(pump, return_exceptions=True)


class NavigationExpectation:
    """Wait for a new navigation caused by the enclosed action.

    The timeout covers the action and the wait. Engine navigation chains are
    followed; a subsequent explicit View load supersedes the observed navigation.
    """

    def __init__(self, page, wait_until, timeout):
        self.page, self.wait_until, self.timeout = page, wait_until, timeout
        self.pending = None
        self.timer = None
        self.expired = False
        self.used = False

    async def __aenter__(self):
        if self.used:
            raise RuntimeError("Navigation expectation cannot be reused")
        self.used = True
        driver = self.page._driver
        driver._check()
        self.pending = self.page.view._state.expect_navigation(self.wait_until, self.timeout)
        self.owner = asyncio.current_task()
        self.cancellations = getattr(self.owner, "cancelling", lambda: 0)()
        self.timer = driver.loop.call_at(self.pending.deadline, self._expire)
        return self

    def _expire(self):
        self.expired = True
        self.owner.cancel()

    async def __aexit__(self, exc_type, exc, traceback):
        try:
            if exc_type is None:
                remaining = self.pending.deadline - self.pending.loop.time()
                if remaining <= 0:
                    raise TimeoutError("Navigation timed out")
                await self.page._driver._run(
                    self.pending.result(), timeout=remaining, render=self.wait_until == "settled"
                )
        except asyncio.CancelledError:
            if self._own_timeout():
                raise TimeoutError("Navigation timed out") from None
            raise
        finally:
            self.timer.cancel()
            self.pending.close()
        if self._own_timeout() and exc_type in (None, asyncio.CancelledError):
            raise TimeoutError("Navigation timed out") from None
        return False

    def _own_timeout(self):
        if not self.expired:
            return False
        self.expired = False
        uncancel = getattr(self.owner, "uncancel", None)
        # Python 3.10 has no cancellation counter. On newer versions, preserve
        # an independent cancellation received while this timeout was active.
        return uncancel is None or uncancel() <= self.cancellations


class ScriptPage:
    """Script conveniences over a borrowed View, using one shared ScriptDriver."""

    def __init__(self, driver, view):
        self._driver = driver
        self._view = view

    @property
    def view(self):
        return self._view

    async def wait_ready(self, timeout=30):
        await self._driver._run(self.view.wait_ready(timeout), timeout=timeout)

    async def wait_settled(self, timeout=30):
        await self._driver._run(self.view.wait_settled(timeout), timeout=timeout, render=True)

    async def wait_until(self, predicate, timeout=30, *, render=False):
        return await self._driver._run(
            self.view.wait_until(predicate, timeout), timeout=timeout, render=render
        )

    async def wait_for_selector(self, selector, timeout=30, *, render=False):
        return await self._driver._run(
            self.view.wait_for_selector(selector, timeout), timeout=timeout, render=render
        )

    async def evaluate(self, source, timeout=30, *, render=True):
        # Arbitrary Promises may depend on rAF/layout, which beta.2 dispatches
        # during Render(). Plain values still finish before any step is requested.
        return await self._driver._run(
            self.view.evaluate_async(source), timeout=timeout, render=render
        )

    def expect_navigation(self, *, wait_until="ready", timeout=30):
        return NavigationExpectation(self, wait_until, timeout)

    async def navigate(self, url, *, wait_until="ready", timeout=30):
        async with self.expect_navigation(wait_until=wait_until, timeout=timeout):
            self.view.load_url(url)

    async def load_html(self, html, url="", *, wait_until="ready", timeout=30):
        async with self.expect_navigation(wait_until=wait_until, timeout=timeout):
            self.view.load_html(html, url)
