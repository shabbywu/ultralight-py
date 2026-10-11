import asyncio
import gc
import sys
import weakref

from cases import load

from ultralight_py import ErrorCode, JavaScriptError, Runtime, UltralightError, _native
from ultralight_py.integrations.asyncio import install, run

runtime = Runtime()
view = runtime.create_view(16, 16)
load(runtime, view, "<body>")


async def main():
    assert await view.evaluate_async("42") == 42
    assert await view.evaluate_async("new Promise(r => setTimeout(() => r(6), 10))") == 6
    assert await view.evaluate_async("Promise.resolve({answer:42})") == {"answer": 42}
    try:
        await view.evaluate_async('Promise.reject(new Error("rejected"))')
    except JavaScriptError as error:
        assert "rejected" in str(error)
    else:
        raise AssertionError("rejection lost")
    with view.evaluate_handle("(x)=>Promise.resolve(x+1)") as fn, await fn.call_async(4) as result:
        assert result.to_python() == 5
    with view.evaluate_handle("42") as plain:
        try:
            await plain.await_result()
        except TypeError:
            pass
        else:
            raise AssertionError("non Promise accepted")

    async def double(n):
        await asyncio.sleep(0.01)
        return n * 2

    view.bind_function("double", double)
    assert await view.evaluate_async("double(21)") == 42
    assert await view.evaluate_async("Promise.all([double(2),double(3)])") == [4, 6]

    async def fail():
        raise ValueError("python failure")

    view.bind_function("fail", fail)
    try:
        await view.evaluate_async("fail()")
    except JavaScriptError as error:
        assert "python failure" in str(error)
    else:
        raise AssertionError("Python rejection lost")

    class Counter:
        def __init__(self, n):
            self.n = n

        async def value(self):
            await asyncio.sleep(0.002)
            return self.n

    view.bind_object("left", Counter(1))
    view.bind_object("right", Counter(9))
    assert await view.evaluate_async("Promise.all([left.value(), right.value()])") == [1, 9]

    cancelled = asyncio.Event()

    async def endless():
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    binding = view.bind_function("endless", endless)
    view.evaluate_handle("endless()").close()
    await asyncio.sleep(0.01)
    binding.close()
    await asyncio.wait_for(cancelled.wait(), 1)

    shared = asyncio.get_running_loop().create_future()
    binding = view.bind_function("shared", lambda: shared)
    view.evaluate_handle("shared()").close()
    binding.close()
    assert not shared.cancelled()
    shared.set_result(9)

    cancelled_shared = asyncio.get_running_loop().create_future()
    view.bind_function("cancelledShared", lambda: cancelled_shared)
    pending_cancel = asyncio.create_task(view.evaluate_async("cancelledShared()"))
    await asyncio.sleep(0)
    cancelled_shared.cancel()
    try:
        await pending_cancel
    except JavaScriptError as error:
        assert "CancelledError" in str(error)
    else:
        raise AssertionError("cancelled Python Future did not reject the JS Promise")

    waiting = asyncio.create_task(view.evaluate_async("new Promise(()=>{})"))
    await asyncio.sleep(0)
    waiting.cancel()
    try:
        await waiting
    except asyncio.CancelledError:
        pass
    waiting = asyncio.create_task(view.evaluate_async("new Promise(()=>{})"))
    await asyncio.sleep(0)
    view.load_html("<body>new page")
    try:
        await waiting
    except UltralightError as error:
        assert error.code == ErrorCode.PageGone
    else:
        raise AssertionError("navigation left waiter alive")


async def keyword_calls():
    view.bind_function("sync", lambda *, value: value + 1)
    assert await view.evaluate_async("Python.call(sync, [], {value:41})") == 42

    async def immediate(*, value):
        return value + 1

    async def delayed(value, *, scale):
        await asyncio.sleep(0.002)
        return value * scale

    async def fail(*, message):
        raise ValueError(message)

    view.bind_function("immediate", immediate)
    view.bind_function("delayed", delayed)
    view.bind_function("fail", fail)
    assert await view.evaluate_async("Python.call(immediate, [], {value:41})") == 42
    assert await view.evaluate_async("Python.call(delayed, [21], {scale:2})") == 42
    try:
        await view.evaluate_async('Python.call(fail, [], {message:"keyword failure"})')
    except JavaScriptError as error:
        assert "keyword failure" in str(error)
    else:
        raise AssertionError("Python.call lost async rejection")

    class Counter:
        def __init__(self, value):
            self.value = value

        async def add(self, *, amount):
            await asyncio.sleep(0.002)
            return self.value + amount

    view.bind_object("left", Counter(1))
    view.bind_object("right", Counter(10))
    assert await view.evaluate_async(
        "Promise.all([Python.call(left.add, [], {amount:2}), "
        "Python.call(right.add, [], {amount:3})])"
    ) == [3, 13]


async def keyword_lifecycle():
    started = {name: asyncio.Event() for name in ("left", "right", "nav", "close")}
    cancelled = {name: asyncio.Event() for name in started}

    async def endless(*, name):
        started[name].set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled[name].set()

    left = view.bind_function("left", endless)
    view.bind_function("right", endless)
    view.evaluate_handle('Python.call(left, [], {name:"left"})').close()
    view.evaluate_handle('Python.call(right, [], {name:"right"})').close()
    await started["left"].wait()
    await started["right"].wait()
    left.close()
    await asyncio.wait_for(cancelled["left"].wait(), 1)
    assert not cancelled["right"].is_set()
    view.unbind("right")
    await asyncio.wait_for(cancelled["right"].wait(), 1)

    shared = asyncio.get_running_loop().create_future()
    binding = view.bind_function("shared", lambda: shared)
    view.evaluate_handle("Python.call(shared, [])").close()
    binding.close()
    assert not shared.cancelled()
    shared.set_result(9)

    view.bind_function("endless", endless)
    view.evaluate_handle('Python.call(endless, [], {name:"nav"})').close()
    await started["nav"].wait()
    ready = asyncio.Event()
    view.set_callbacks(dom_ready=lambda e: ready.set() if e.is_main_frame else None)
    view.load_html("<body>new document")
    await asyncio.wait_for(cancelled["nav"].wait(), 1)
    await asyncio.wait_for(ready.wait(), 1)
    view.bind_function("endless", endless)
    waiting = asyncio.create_task(view.evaluate_async('Python.call(endless, [], {name:"close"})'))
    await started["close"].wait()
    view.close()
    await asyncio.wait_for(cancelled["close"].wait(), 1)
    try:
        await waiting
    except UltralightError as error:
        assert error.code == ErrorCode.PageGone
    else:
        raise AssertionError("closing View left Python.call waiter alive")


async def manual():
    future = asyncio.create_task(view.evaluate_async("new Promise(r=>globalThis.finish=r)"))
    await asyncio.sleep(0)
    view.evaluate("finish(7)")
    await asyncio.sleep(0.02)

    # JS microtasks may run on evaluation itself; use Python delivery to verify gating.
    async def answer():
        return 8

    view.bind_function("answer", answer)
    pending = asyncio.create_task(view.evaluate_async("answer()"))
    await asyncio.sleep(0.02)
    assert not pending.done()
    runtime.update()
    for _ in range(10):
        await asyncio.sleep(0.001)
        runtime.update()
        if pending.done():
            break
    assert await pending == 8

    class Result:
        pass

    result = Result()
    ref = weakref.ref(result)
    external = asyncio.get_running_loop().create_future()
    binding = view.bind_function("late", lambda future=external: future)
    view.evaluate_handle("late()").close()
    external.set_result(result)
    await asyncio.sleep(0)
    binding.close()
    del result, external
    runtime.update()
    await asyncio.sleep(0)
    gc.collect()

    _native._drain()
    gc.collect()
    assert ref() is None
    assert await future == 7
    waiting = asyncio.create_task(view.evaluate_async("new Promise(()=>{})"))
    await asyncio.sleep(0)
    view.close()
    try:
        await waiting
    except UltralightError as error:
        assert error.code == ErrorCode.PageGone


async def failure():
    driver = install(runtime, 0.001)
    try:
        install(runtime)
    except RuntimeError:
        pass
    else:
        raise AssertionError("duplicate driver accepted")
    waiting = asyncio.create_task(view.evaluate_async("new Promise(()=>{})"))

    def broken():
        raise ValueError("driver failure")

    runtime.update = broken
    error = await driver.failure
    assert str(error) == "driver failure"
    try:
        await waiting
    except ValueError:
        pass
    assert driver.closed


async def run_failure():
    def broken():
        raise ValueError("run driver failure")

    runtime.update = broken
    await view.evaluate_async("new Promise(()=>{})")


try:
    if sys.argv[1] == "run_failure":
        try:
            run(run_failure(), runtime=runtime, update_interval=0.001)
        except ValueError as error:
            assert str(error) == "run driver failure"
        else:
            raise AssertionError("run swallowed driver failure")
    elif sys.argv[1] in {"main", "keyword_calls", "keyword_lifecycle"}:
        run(globals()[sys.argv[1]](), runtime=runtime, update_interval=0.001)
    else:
        asyncio.run(globals()[sys.argv[1]]())
finally:
    runtime.close()
