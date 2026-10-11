"""Internal asyncio loop ownership, Promise waits and delayed deliveries."""

from __future__ import annotations

import asyncio
import inspect

from ultralight_py import _support
from ultralight_py import api as _api


def get_runtime():
    return _api.Runtime._instance


def associate(runtime):
    _support.ensure_in_main_thread()
    loop = asyncio.get_running_loop()
    previous = getattr(runtime, "_async_loop", None)
    if previous is not None and previous is not loop and not previous.is_closed():
        raise RuntimeError("Runtime is already associated with another asyncio loop")
    runtime._async_loop = loop
    if not hasattr(runtime, "_async_work"):
        runtime._async_work = set()
        runtime._async_deliveries = []
    return loop


def stop(runtime, error):
    for work in tuple(getattr(runtime, "_async_work", ())):
        work(error)
    getattr(runtime, "_async_deliveries", []).clear()


def flush(runtime):
    pending = getattr(runtime, "_async_deliveries", [])
    runtime._async_deliveries = []
    for deliver in pending:
        deliver()


async def await_result(value):
    runtime = get_runtime()
    loop = associate(runtime)
    future = loop.create_future()

    def settled(native, error):
        if future.done():
            if native is not None:
                native.close()
            return
        if error is not None:
            future.set_exception(error)
        else:
            future.set_result(_api.JSValue(native))

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


def start(awaitable, delivery):
    runtime = get_runtime()
    try:
        loop = associate(runtime)
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
            error = asyncio.CancelledError() if task.cancelled() else task.exception()
            try:
                if error is None:
                    delivery.settle(task.result(), False)
                else:
                    delivery.settle(str(error) or type(error).__name__, True)
            finally:
                delivery.close()

        runtime._async_deliveries.append(deliver)

    delivery.on_cancel(stop)
    runtime._async_work.add(stop)
    task.add_done_callback(done)
