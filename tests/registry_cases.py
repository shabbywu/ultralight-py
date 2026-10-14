"""Real-engine registry scenarios; isolate the permanent Renderer singleton."""

import asyncio
import gc
import sys
import weakref

from ultralight_py import API, Runtime, UltralightError
from ultralight_py.scripting import ScriptDriver


async def main():
    runtime = Runtime()
    first = runtime.create_view(200, 100)
    second = runtime.create_view(200, 100)
    api = API("app")

    @api.register
    def echo(value):
        return value

    @api.register(name="plus")
    def add(value):
        return value + 1

    assert echo("direct") == "direct" and add(2) == 3

    class Model:
        def __init__(self):
            self.items = [1, 2]

    model = Model()
    reference = weakref.ref(model)
    api.register_object("model", model, members=["items"])
    api.attach(first)
    conflicting = API("app")
    try:
        conflicting.attach(first)
    except UltralightError:
        pass
    else:
        raise AssertionError("duplicate namespace accepted")
    conflicting.close()
    api.attach(second)
    api.attach(first)
    failures = []
    runtime.set_error_handler(failures.append)
    async with ScriptDriver.auto(runtime) as driver:
        html = (
            "<script>globalThis.answer=app.plus(app.echo(41)); globalThis.saved=app.model;</script>"
        )
        await driver.page(first).load_html(html)
        await driver.page(second).load_html(html)
        assert first.evaluate("answer") == second.evaluate("answer") == 42
        assert first.evaluate("app.model.items === app.model.items")
        assert first.evaluate("Python.getitem(app.model.items,0)") == 1
        api.register(lambda value: value + 2, name="plus")
        assert first.evaluate("app.plus(40)") == second.evaluate("app.plus(40)") == 42
        await driver.page(first).load_html(html)
        assert first.evaluate("answer") == 43
        api.unregister("plus")
        assert (
            first.evaluate("typeof app.plus") == second.evaluate("typeof app.plus") == "undefined"
        )
        api.detach(first)
        assert first.evaluate("typeof app") == "undefined"
        try:
            first.evaluate("saved.items")
        except UltralightError:
            pass
        else:
            raise AssertionError("detached proxy remained usable")
        await driver.page(first).load_html("<script>globalThis.absent=typeof app;</script>")
        assert first.evaluate("absent") == "undefined"
        api.attach(first)
        assert first.evaluate("app.echo(12)") == 12
        first.close()
        second.close()
    assert not failures, failures
    del model
    gc.collect()
    assert reference() is not None, "registry must retain definitions after Views close"
    api.close()
    gc.collect()
    assert reference() is None, "API.close must release registered objects"
    runtime.close()


async def asynchronous():
    runtime = Runtime()
    view = runtime.create_view(200, 100)
    api = API("app")
    started = asyncio.Event()
    finished = asyncio.Event()

    @api.register
    async def pending():
        started.set()
        try:
            await asyncio.Future()
        finally:
            finished.set()

    api.attach(view)
    async with ScriptDriver.auto(runtime) as driver:
        await driver.page(view).load_html(
            "<script>globalThis.promise=app.pending();promise.catch(()=>{});</script>"
        )
        await asyncio.wait_for(started.wait(), 2)
        api.detach(view)
        await asyncio.wait_for(finished.wait(), 2)
        api.attach(view)
        view.close()
    api.close()
    runtime.close()


if __name__ == "__main__":
    asyncio.run({"main": main, "async": asynchronous}[sys.argv[1]]())
