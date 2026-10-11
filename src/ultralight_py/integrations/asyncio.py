"""Optional asyncio timer for a Python-hosted Ultralight runtime."""

from __future__ import annotations

import asyncio
import math

from ultralight_py import _asyncio, _native, _support


class Driver:
    def __init__(self, runtime, interval):
        self.runtime = runtime
        self.loop = _asyncio.associate(runtime)
        self.interval = interval
        self.closed = False
        self.failure = self.loop.create_future()
        self._timer = self.loop.call_later(interval, self._tick)

    def _tick(self):
        if self.closed:
            return
        # Route every driver failure to run() and revoke cross-language waits.
        try:
            self.runtime.update()
        except BaseException as error:  # noqa: BLE001
            self.failure.set_result(error)
            self.close(error)
            return
        self._timer = self.loop.call_later(self.interval, self._tick)

    def close(self, error=None):
        _support.ensure_in_main_thread()
        if self.closed:
            return
        self.closed = True
        self._timer.cancel()
        self.runtime._async_driver = None
        _asyncio.stop(
            self.runtime,
            error or _native._make_error(_native.ErrorCode.Closed, "asyncio driver closed"),
        )

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def install(runtime, update_interval=1 / 60):
    _support.ensure_in_main_thread()
    if (
        isinstance(update_interval, bool)
        or not math.isfinite(update_interval)
        or update_interval <= 0
    ):
        raise ValueError("update_interval must be finite and positive")
    if runtime.closed:
        raise _native._make_error(_native.ErrorCode.Closed, "Runtime is closed")
    if getattr(runtime, "_async_driver", None) is not None:
        raise RuntimeError("Runtime already has an asyncio driver")
    driver = Driver(runtime, update_interval)
    runtime._async_driver = driver
    return driver


def run(main, *, runtime, update_interval=1 / 60):
    async def entry():
        driver = install(runtime, update_interval)
        task = asyncio.create_task(main)
        try:
            done, _ = await asyncio.wait(
                (task, driver.failure), return_when=asyncio.FIRST_COMPLETED
            )
            if driver.failure in done:
                raise driver.failure.result()
            return await task
        finally:
            driver.close()
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    return asyncio.run(entry())
