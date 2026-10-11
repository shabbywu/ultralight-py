"""Optional asyncio timer for a Python-hosted Ultralight runtime."""
from __future__ import annotations

import asyncio
import inspect
import math
from .._support import _main_thread
from .. import _native


def _runtime():
    from ..api import Runtime
    return Runtime._instance


def _associate(runtime):
    _main_thread()
    loop = asyncio.get_running_loop()
    previous = getattr(runtime, '_async_loop', None)
    if previous is not None and previous is not loop and not previous.is_closed():
        raise RuntimeError('Runtime is already associated with another asyncio loop')
    runtime._async_loop = loop
    if not hasattr(runtime, '_async_work'):
        runtime._async_work = set()
        runtime._async_deliveries = []
    return loop


def _stop(runtime, error):
    for work in tuple(getattr(runtime, '_async_work', ())):
        work(error)
    getattr(runtime, '_async_deliveries', []).clear()


def _flush(runtime):
    pending = getattr(runtime, '_async_deliveries', [])
    runtime._async_deliveries = []
    for deliver in pending:
        deliver()


async def _await(value):
    from ..api import JSValue
    runtime = _runtime()
    loop = _associate(runtime)
    future = loop.create_future()

    def settled(native, error):
        if future.done():
            if native is not None:
                native.close()
            return
        if error is not None:
            future.set_exception(error)
        else:
            future.set_result(JSValue(native))

    def stop(error):
        watch.close()
        settled(None, error)

    watch = value._native.watch(settled)
    runtime._async_work.add(stop)
    try:
        return await future
    finally:
        watch.close()
        runtime._async_work.discard(stop)


class Driver:
    def __init__(self, runtime, interval):
        self.runtime = runtime
        self.loop = _associate(runtime)
        self.interval = interval
        self.closed = False
        self.failure = self.loop.create_future()
        self._timer = self.loop.call_later(interval, self._tick)

    def _tick(self):
        if self.closed:
            return
        try:
            self.runtime.update()
        except BaseException as error:
            self.failure.set_result(error)
            self.close(error)
            return
        self._timer = self.loop.call_later(self.interval, self._tick)

    def close(self, error=None):
        _main_thread()
        if self.closed:
            return
        self.closed = True
        self._timer.cancel()
        self.runtime._async_driver = None
        _stop(self.runtime, error or _native._make_error(_native.ErrorCode.Closed, 'asyncio driver closed'))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def install(runtime, update_interval=1 / 60):
    _main_thread()
    if isinstance(update_interval, bool) or not math.isfinite(update_interval) or update_interval <= 0:
        raise ValueError('update_interval must be finite and positive')
    if runtime.closed:
        raise _native._make_error(_native.ErrorCode.Closed, 'Runtime is closed')
    if getattr(runtime, '_async_driver', None) is not None:
        raise RuntimeError('Runtime already has an asyncio driver')
    driver = Driver(runtime, update_interval)
    runtime._async_driver = driver
    return driver


def run(main, *, runtime, update_interval=1 / 60):
    async def entry():
        driver = install(runtime, update_interval)
        task = asyncio.create_task(main)
        try:
            done, _ = await asyncio.wait((task, driver.failure), return_when=asyncio.FIRST_COMPLETED)
            if driver.failure in done:
                raise driver.failure.result()
            return await task
        finally:
            driver.close()
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    return asyncio.run(entry())


def _start(awaitable, delivery):
    runtime = _runtime()
    try:
        loop = _associate(runtime)
        owned = not isinstance(awaitable, asyncio.Future)
        task = asyncio.ensure_future(awaitable, loop=loop)
    except BaseException:
        if inspect.iscoroutine(awaitable):
            awaitable.close()
        raise

    def stop(error=None):
        delivery.close()
        task.remove_done_callback(done)
        runtime._async_work.discard(stop)
        if owned:
            task.cancel()
            # Retrieve exceptions from tasks which suppress cancellation.
            task.add_done_callback(lambda t: None if t.cancelled() else t.exception())

    def done(task):
        def deliver():
            if stop not in runtime._async_work:
                return
            runtime._async_work.discard(stop)
            try:
                result = task.result()
            except BaseException as error:
                delivery.settle(str(error) or type(error).__name__, True)
            else:
                delivery.settle(result, False)
            finally:
                delivery.close()
        runtime._async_deliveries.append(deliver)

    delivery.on_cancel(stop)
    runtime._async_work.add(stop)
    task.add_done_callback(done)
