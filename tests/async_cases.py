import asyncio
import sys
from ultralight_py import Runtime, JavaScriptError, UltralightError, ErrorCode
from ultralight_py.integrations.asyncio import install, run
from cases import load

runtime = Runtime()
view = runtime.create_view(16, 16)
load(runtime, view, '<body>')

async def main():
    assert await view.evaluate_async('42') == 42
    assert await view.evaluate_async('new Promise(r => setTimeout(() => r(6), 10))') == 6
    assert await view.evaluate_async('Promise.resolve({answer:42})') == {'answer':42}
    try:
        await view.evaluate_async('Promise.reject(new Error("rejected"))')
    except JavaScriptError as error:
        assert 'rejected' in str(error)
    else:
        raise AssertionError('rejection lost')
    with view.evaluate_handle('(x)=>Promise.resolve(x+1)') as fn:
        with await fn.call_async(4) as result:
            assert result.to_python() == 5
    with view.evaluate_handle('42') as plain:
        try:
            await plain.await_result()
        except TypeError:
            pass
        else:
            raise AssertionError('non Promise accepted')

    async def double(n):
        await asyncio.sleep(.01)
        return n * 2
    view.bind_function('double', double)
    assert await view.evaluate_async('double(21)') == 42
    assert await view.evaluate_async('Promise.all([double(2),double(3)])') == [4,6]
    async def fail():
        raise ValueError('python failure')
    view.bind_function('fail', fail)
    try:
        await view.evaluate_async('fail()')
    except JavaScriptError as error:
        assert 'python failure' in str(error)
    else:
        raise AssertionError('Python rejection lost')

    class Counter:
        def __init__(self, n):
            self.n = n
        async def value(self):
            await asyncio.sleep(.002)
            return self.n
    view.bind_object('left', Counter(1))
    view.bind_object('right', Counter(9))
    assert await view.evaluate_async('Promise.all([left.value(), right.value()])') == [1, 9]

    cancelled = asyncio.Event()
    async def endless():
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()
    binding = view.bind_function('endless', endless)
    view.evaluate_handle('endless()').close()
    await asyncio.sleep(.01)
    binding.close()
    await asyncio.wait_for(cancelled.wait(), 1)

    shared = asyncio.get_running_loop().create_future()
    binding = view.bind_function('shared', lambda: shared)
    view.evaluate_handle('shared()').close()
    binding.close()
    assert not shared.cancelled()
    shared.set_result(9)

    waiting = asyncio.create_task(view.evaluate_async('new Promise(()=>{})'))
    await asyncio.sleep(0)
    waiting.cancel()
    try:
        await waiting
    except asyncio.CancelledError:
        pass
    waiting = asyncio.create_task(view.evaluate_async('new Promise(()=>{})'))
    await asyncio.sleep(0)
    view.load_html('<body>new page')
    try:
        await waiting
    except UltralightError as error:
        assert error.code == ErrorCode.PageGone
    else:
        raise AssertionError('navigation left waiter alive')

async def manual():
    future = asyncio.create_task(view.evaluate_async('new Promise(r=>globalThis.finish=r)'))
    await asyncio.sleep(0)
    view.evaluate('finish(7)')
    await asyncio.sleep(.02)
    # JS microtasks may run on evaluation itself; use Python delivery to verify gating.
    async def answer():
        return 8
    view.bind_function('answer', answer)
    pending = asyncio.create_task(view.evaluate_async('answer()'))
    await asyncio.sleep(.02)
    assert not pending.done()
    runtime.update()
    for _ in range(10):
        await asyncio.sleep(.001)
        runtime.update()
        if pending.done():
            break
    assert await pending == 8
    import gc
    import weakref
    class Result:
        pass
    result = Result()
    ref = weakref.ref(result)
    external = asyncio.get_running_loop().create_future()
    binding = view.bind_function('late', lambda: external)
    view.evaluate_handle('late()').close()
    external.set_result(result)
    await asyncio.sleep(0)
    binding.close()
    del result, external
    runtime.update()
    await asyncio.sleep(0)
    gc.collect()
    from ultralight_py import _native
    _native._drain()
    gc.collect()
    assert ref() is None
    assert await future == 7
    waiting = asyncio.create_task(view.evaluate_async('new Promise(()=>{})'))
    await asyncio.sleep(0)
    view.close()
    try:
        await waiting
    except UltralightError as error:
        assert error.code == ErrorCode.PageGone

async def failure():
    driver = install(runtime, .001)
    try:
        install(runtime)
    except RuntimeError:
        pass
    else:
        raise AssertionError('duplicate driver accepted')
    waiting = asyncio.create_task(view.evaluate_async('new Promise(()=>{})'))
    def broken():
        raise ValueError('driver failure')
    runtime.update = broken
    error = await driver.failure
    assert str(error) == 'driver failure'
    try:
        await waiting
    except ValueError:
        pass
    assert driver.closed

async def run_failure():
    def broken():
        raise ValueError('run driver failure')
    runtime.update = broken
    await view.evaluate_async('new Promise(()=>{})')

try:
    if sys.argv[1] == 'run_failure':
        try:
            run(run_failure(), runtime=runtime, update_interval=.001)
        except ValueError as error:
            assert str(error) == 'run driver failure'
        else:
            raise AssertionError('run swallowed driver failure')
    elif sys.argv[1] == 'main':
        run(main(), runtime=runtime, update_interval=.001)
    else:
        asyncio.run(globals()[sys.argv[1]]())
finally:
    runtime.close()
