"""AppCore integration scenarios requiring a native desktop session."""

import asyncio
import gc
import sys
import weakref

from ultralight_py import API, Application, ErrorCode, Runtime, UltralightError
from ultralight_py.integrations import asyncio as integration
from ultralight_py.scripting import ScriptDriver


def expect(code, function):
    try:
        function()
    except UltralightError as error:
        assert error.code == code, error
    else:
        raise AssertionError(f"expected {code}")


async def smoke(cpu):
    app = Application(force_cpu_renderer=cpu)
    runtime = app.runtime
    assert Runtime() is runtime
    session = runtime.create_session("window-session")
    window = app.create_window(420, 280, title="AppCore smoke", session=session)
    other = app.create_window(240, 160)
    api = API("app")
    errors = []
    runtime.set_error_handler(errors.append)

    @api.register
    async def add(value):
        await asyncio.sleep(0)
        return value + 1

    api.attach(window.view)
    window.view.load_html("""<meta charset='utf-8'><p>中文系统字体</p><input id='editor'>
<script>globalThis.ticks=0;setInterval(()=>ticks++,20);globalThis.answer=app.add(41);</script>""")
    other.view.load_html("<p>second window</p>")
    task = asyncio.create_task(app.run_async())
    try:
        await asyncio.wait_for(window.view.wait_settled(), 10)
        await asyncio.wait_for(other.view.wait_ready(), 10)
        assert await window.view.evaluate_async("answer") == 42
        await window.view.wait_until(lambda: window.view.evaluate("ticks") >= 2)
        assert abs(window.view.evaluate("devicePixelRatio") - window.device_scale) < 0.01
        assert window.device_width == round(window.width * window.device_scale)
        assert window.device_height == round(window.height * window.device_scale)
        expect(ErrorCode.InvalidArgument, lambda: app.create_window(120, 80, view=window.view))
        assert not window.view.closed
        window.title = "updated"
        assert window.title == "updated"
        if cpu:
            pixels = window.view.copy_pixels()
            assert pixels.width == window.device_width and pixels.height == window.device_height
        window.view.focus()
        expect(ErrorCode.Unsupported, runtime.update)
        expect(ErrorCode.Unsupported, lambda: integration.install(runtime))
        expect(ErrorCode.Unsupported, lambda: ScriptDriver.auto(runtime))
        expect(ErrorCode.Busy, app.run_once)
        async with ScriptDriver(runtime) as driver:
            assert await driver.page(window.view).evaluate("app.add(10)") == 11
        waiting = asyncio.create_task(window.view.wait_until(lambda: False, timeout=30))
        await asyncio.sleep(0)
        observed = []
        window.on("closed", lambda event: observed.append((window.view.closed, app.closed)))
        window.close()
        assert window.closed and window.view.closed and not app.closed
        assert observed == [(True, False)]
        try:
            await waiting
        except UltralightError as error:
            assert error.code == ErrorCode.Closed
        else:
            raise AssertionError("window wait did not finish")
        assert not session.closed
        other.close()
        await asyncio.wait_for(task, 5)
        assert app.closed and runtime.closed and session.closed
        assert not app.run_once()
        expect(ErrorCode.Closed, runtime.update)
        expect(ErrorCode.Closed, lambda: integration.install(runtime))
        expect(ErrorCode.Closed, lambda: ScriptDriver.auto(runtime))
        assert not api.closed
        api.close()
        assert not errors, errors
    finally:
        app.close()
        await asyncio.gather(task, return_exceptions=True)
        api.close()


async def closing(case):
    app = Application(force_cpu_renderer=True)
    session = app.runtime.create_session("closing")
    existing = app.runtime.create_view(200, 100, session=session)
    window = app.create_window(240, 160, view=existing)
    assert window.view is existing
    api = API("app")
    entered = asyncio.Event()
    cancelled = asyncio.Event()

    class Model:
        value = 42

    model = Model()
    ref = weakref.ref(model)
    api.register_object("model", model)

    @api.register
    async def pending():
        entered.set()
        try:
            await asyncio.Future()
        finally:
            cancelled.set()

    api.attach(existing)
    existing.load_html("<script>globalThis.result=app.pending();result.catch(()=>{});</script>")
    task = asyncio.create_task(app.run_async())
    await asyncio.wait_for(entered.wait(), 10)
    waiting = asyncio.create_task(existing.evaluate_async("result"))
    await asyncio.sleep(0)
    if case == "runtime":
        app.runtime.close()
    elif case == "session":
        session.close(force_close=True)
        assert existing.closed and not window.closed and not app.closed
        window.close()
    elif case == "view":
        existing.close()
        assert not window.closed
        window.close()
    elif case == "cancel":
        task.cancel()
    elif case == "failure":

        def fail():
            raise RuntimeError("driver failed")

        app._advance = fail
    else:
        window.close()
    outcomes = await asyncio.gather(task, return_exceptions=True)
    if case == "failure":
        assert isinstance(outcomes[0], RuntimeError) and str(outcomes[0]) == "driver failed"
    await asyncio.wait_for(cancelled.wait(), 5)
    try:
        await waiting
    except UltralightError as error:
        assert error.code in (ErrorCode.PageGone, ErrorCode.Closed)
    else:
        raise AssertionError("Promise wait survived closure")
    assert app.closed and window.closed and existing.closed
    del model
    gc.collect()
    assert ref() is not None
    api.close()
    gc.collect()
    assert ref() is None
    app.close()


def synchronous():
    app = Application(force_cpu_renderer=True)
    window = app.create_window(240, 160)
    api = API("app")

    @api.register
    async def quit():
        await asyncio.sleep(0.02)
        window.close()

    api.attach(window.view)
    window.view.load_html("<script>app.quit().catch(()=>{});</script>")
    app.run()
    assert app.closed and window.closed
    api.close()


async def reentrant():
    app = Application(force_cpu_renderer=True)
    window = app.create_window(240, 160)
    window.view.on("dom_ready", lambda event: window.close())
    window.on("closed", lambda event: app.close())
    window.view.load_html("<p>close during Renderer dispatch</p>")
    await asyncio.wait_for(app.run_async(), 10)
    assert app.closed and window.closed and window.view.closed


if __name__ == "__main__":
    case = sys.argv[1]
    if case == "sync":
        synchronous()
    elif case in ("cpu", "gpu"):
        asyncio.run(smoke(case == "cpu"))
    elif case == "reentrant":
        asyncio.run(reentrant())
    else:
        asyncio.run(closing(case))
