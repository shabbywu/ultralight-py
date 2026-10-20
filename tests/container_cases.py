"""Shared container integration cases, each run in a fresh native process."""

import asyncio
import gc
import sys
import threading
import weakref

from cases import load, raises

from ultralight_py import (
    ErrorCode,
    JavaScriptError,
    JSArray,
    JSObject,
    Runtime,
    UltralightError,
    undefined,
)
from ultralight_py.integrations.asyncio import install
from ultralight_py.scripting import ScriptDriver


def arrays():
    with Runtime() as runtime:
        view = runtime.create_view(16, 16)
        load(runtime, view, "<body>")
        data = [3, 1, 2]
        view.bind_object("data", data)
        assert view.evaluate("Array.isArray(data) && data instanceof Array")
        assert view.evaluate("[...data]") == [3, 1, 2]
        assert view.evaluate("data.map(x=>x*2)") == [6, 2, 4]
        assert view.evaluate("data.filter(x=>x>1)") == [3, 2]
        assert view.evaluate("data.reduce((a,b)=>a+b,0)") == 6
        assert view.evaluate("data.concat([4])") == [3, 1, 2, 4]
        assert view.evaluate("data.at(-1)") == 2
        assert view.evaluate("data[-1]") is undefined
        assert view.evaluate("data.sort((a,b)=>a-b)===data")
        assert data == [1, 2, 3]
        assert view.evaluate("data.push(4)") == 4
        assert view.evaluate("data.pop()") == 4
        assert view.evaluate("data.shift()") == 1
        assert view.evaluate("data.unshift(5,6)") == 4
        assert view.evaluate("data.splice(1,2,7,8,9)") == [6, 2]
        assert data == [5, 7, 8, 9, 3]
        assert view.evaluate("data.reverse()===data && data.fill(0,1,3)===data")
        view.evaluate("data.copyWithin(0,3)")
        assert data == [7, 5, 0, 7, 5]
        view.evaluate("delete data[1]; data[7]=9")
        assert data == [7, undefined, 0, 7, 5, undefined, undefined, 9]
        assert view.evaluate("1 in data")
        assert view.evaluate("Object.keys(data)") == [str(i) for i in range(8)]
        assert view.evaluate("JSON.stringify(data)") == "[7,null,0,7,5,null,null,9]"
        view.evaluate("data.length=2; data.length=4")
        assert data == [7, undefined, undefined, undefined]
        data[:] = [42]
        assert view.evaluate("Reflect.ownKeys(data)") == ["0", "length"]
        assert view.evaluate("Object.getOwnPropertyDescriptor(data,'length').value") == 1
        assert view.evaluate("Object.getOwnPropertyDescriptor(data,'0').value") == 42
        assert view.evaluate("Object.getOwnPropertyDescriptor(data,'9')") is undefined
        assert view.evaluate("JSON.stringify(data)") == "[42]"
        for script in [
            "data.length=-1",
            "data.length=1.5",
            "data.length=2**32",
            "data.length=1n",
            "data[-1]=8",
            "data.extra=8",
            "Object.freeze(data)",
            "Object.defineProperty(data,'0',{value:9})",
            "Object.setPrototypeOf(data,null)",
        ]:
            raises(JavaScriptError, lambda script=script: view.evaluate(script))
        view.evaluate("data.length=-0")
        assert data == []


def dictionaries():
    with Runtime() as runtime:
        view = runtime.create_view(16, 16)
        load(runtime, view, "<body>")
        data = {1: "integer", "1": "string", "keys": 7, "__proto__": 8, "_secret": 9}
        view.bind_object("data", data)
        assert view.evaluate("data[1]===data['1'] && data[1]==='string'")
        assert view.evaluate("Python.getitem(data,1)") == "integer"
        assert view.evaluate("data.keys") == 7
        assert view.evaluate("data.__proto__") == 8
        assert view.evaluate("data._secret") == 9
        assert view.evaluate("Object.getPrototypeOf(data)") is None
        assert view.evaluate("Object.keys(data)") == ["1", "keys", "__proto__", "_secret"]
        assert (
            view.evaluate("JSON.stringify(data)")
            == '{"1":"string","keys":7,"__proto__":8,"_secret":9}'
        )
        view.evaluate(
            "Object.assign(data,{enabled:true}); delete data.keys; Python.setitem(data,1,'changed')"
        )
        assert data[1] == "changed" and data["enabled"] is True and "keys" not in data
        assert view.evaluate("'enabled' in data && !('absent' in data)")
        assert view.evaluate("data.absent") is undefined
        assert view.evaluate("({...data})") == {
            "1": "string",
            "__proto__": 8,
            "_secret": 9,
            "enabled": True,
        }
        data["nested"] = [1]
        view.evaluate("data.nested.push(2)")
        assert data["nested"] == [1, 2]
        data["10"] = 10
        data["2"] = 2
        assert list(view.evaluate("Object.keys(data)"))[:3] == ["1", "2", "10"]


def js_arrays():
    with Runtime() as runtime:
        view = runtime.create_view(16, 16)
        load(runtime, view, "<body>")
        items = view.evaluate("globalThis.items=[1,2,3]")
        assert isinstance(items, JSArray)
        assert items.to_python() is items
        assert view.evaluate("items") is items
        items.append(4)
        items.insert(-1, 7)
        assert view.evaluate("JSON.stringify(items)") == "[1,2,3,7,4]"
        assert items[-1] == 4 and items[1:4:2] == [2, 7]
        items[1:3] = [8, 9, 10]
        items[::2] = [0, 1, 2]
        assert items == [0, 8, 1, 10, 2, 4]
        raises(ValueError, lambda: items.__setitem__(slice(None, None, 2), []))
        del items[4:0:-2]
        assert items == [0, 8, 10, 4]
        assert items.pop() == 4
        items.reverse()
        items.sort(reverse=True)
        assert items == [10, 8, 0]
        items.extend([6, 7])
        assert items.copy() == [10, 8, 0, 6, 7]
        raises(IndexError, lambda: items[99])
        raises(TypeError, lambda: items["0"])
        view.evaluate("items.length=2; items[0]=42")
        assert items == [42, 8]
        sparse = view.evaluate("[,1,,]")
        assert sparse == [undefined, 1, undefined]
        del sparse[0]
        assert sparse == [1, undefined]
        items.clear()
        assert view.evaluate("items.length") == 0


def js_objects():
    with Runtime() as runtime:
        view = runtime.create_view(16, 16)
        load(runtime, view, "<body>")
        obj = view.evaluate("globalThis.obj={name:'lab',nested:{items:[]}}")
        assert isinstance(obj, JSObject)
        assert obj.to_python() is obj
        assert view.evaluate("obj") is obj
        obj.update(enabled=True)
        obj["nested"]["items"].append(7)
        assert view.evaluate("obj.enabled && obj.nested.items[0]===7")
        view.evaluate("obj.name='updated'")
        assert obj["name"] == "updated"
        assert obj.setdefault("count", 1) == 1
        assert obj.pop("count") == 1
        assert obj.get("missing") is None
        raises(KeyError, lambda: obj["missing"])
        raises(TypeError, lambda: obj[1])
        view.evaluate("Object.defineProperty(obj,'hidden',{value:9})")
        assert "hidden" not in obj
        frozen = view.evaluate("Object.freeze({x:1})")
        raises(JavaScriptError, lambda: frozen.__setitem__("x", 2))
        raises(JavaScriptError, lambda: frozen.__delitem__("x"))
        null = view.evaluate("Object.create(null)")
        null["__proto__"] = "data"
        assert null["__proto__"] == "data"
        del obj["name"]
        assert view.evaluate("'name' in obj") is False


def identity():
    with Runtime() as runtime:
        view = runtime.create_view(16, 16)
        load(runtime, view, "<body>")
        observed = []

        def edit(items, options):
            observed.extend([items, options])
            items.append(options)
            options["owner"] = items
            return items

        view.bind_function("edit", edit)
        assert view.evaluate(
            "globalThis.a=[]; globalThis.b={}; edit(a,b)===a && a[0]===b && b.owner===a"
        )
        a, b = observed
        assert a[0] is b and b["owner"] is a
        assert view.evaluate("a") is a
        py = []
        py.append(py)
        binding = view.bind_object("py", py)
        assert view.evaluate("py[0]===py")
        a.append(py)
        assert a[-1] is py
        py.append(b)
        assert view.evaluate("py[1]===b")
        view.evaluate("a.push(py)")
        view.bind_function("echo", lambda x: x)
        assert view.evaluate("echo(a)===a && echo(b)===b")
        binding.close()
        # JS-owned views survive the revocation of a Python binding.
        assert a[0] is b
        raises(UltralightError, lambda: a[-1], ErrorCode.PageGone)
        root = view.evaluate("globalThis.root={}; root.self=root; root")
        assert root["self"] is root


def snapshots():
    with Runtime() as runtime:
        view = runtime.create_view(16, 16)
        load(runtime, view, "<body>")
        live = view.evaluate("globalThis.data={items:[1]}")
        snapshot = view.evaluate("data", copy=True)
        assert type(snapshot) is dict and type(snapshot["items"]) is list
        snapshot["items"].append(2)
        assert live["items"] == [1]
        assert live.to_python(copy=True) == snapshot | {"items": [1]}
        with view.evaluate_handle("data") as handle:
            child = handle.to_python()
            assert child is live
            assert handle.to_python(copy=True) == {"items": [1]}
        assert live["items"] == [1]  # Temporary handles do not close live views.
        assert view.evaluate("Python.to_value(data)") == {"items": [1]}
        view.bind_object("mixed", [live])
        assert view.evaluate("Python.to_value(mixed)", copy=True) == [{"items": [1]}]
        py = [1, {"nested": [2]}]
        view.bind_object("py", py)
        copied = view.evaluate("py", copy=True)
        copied[1]["nested"].append(3)
        assert py[1]["nested"] == [2]
        cycle = view.evaluate("globalThis.cycle=[]; cycle.push(cycle); cycle")
        assert cycle[0] is cycle
        raises(UltralightError, lambda: cycle.to_python(copy=True), ErrorCode.TraversalLimit)
        deep = view.evaluate("Array.from({length:65}).reduce(a=>[a],[])")
        raises(UltralightError, lambda: deep.to_python(copy=True), ErrorCode.TraversalLimit)
        raises(
            UltralightError,
            lambda: view.evaluate("new Proxy([],{get:()=>NaN})", copy=True),
            ErrorCode.TypeMismatch,
        )


def lifecycle():
    with Runtime() as runtime:
        view = runtime.create_view(16, 16)
        load(runtime, view, "<body>")
        live = view.evaluate("globalThis.data=[]")
        reference = weakref.ref(live)
        del live
        gc.collect()
        assert reference() is None  # Identity caches must not retain Python wrappers.
        live = view.evaluate("data")
        live.close()
        assert live.closed
        replacement = view.evaluate("data")
        assert replacement is not live and not replacement.closed
        errors = []

        def worker():
            try:
                replacement.append(1)
            except UltralightError as error:
                errors.append(error.code)

        thread = threading.Thread(target=worker)
        thread.start()
        thread.join()
        assert errors == [ErrorCode.WrongThread]
        other = runtime.create_view(16, 16)
        load(runtime, other, "<body>")
        echo = other.evaluate_handle("x=>x")
        raises(UltralightError, lambda: echo.call(replacement), ErrorCode.CrossContext)
        load(runtime, view, "<body>next")
        assert replacement.closed
        raises(UltralightError, lambda: replacement.append(2), ErrorCode.PageGone)
        obj = view.evaluate("({})")
        view.close()
        assert obj.closed
        raises(UltralightError, lambda: len(obj), ErrorCode.PageGone)


def asynchronous():
    async def run():
        with Runtime() as runtime:
            view = runtime.create_view(16, 16)
            with install(runtime, update_interval=0.001):
                view.load_html("<body>")
                await view.wait_ready()
                live = await view.evaluate_async("Promise.resolve(globalThis.data=[1])")
                assert isinstance(live, JSArray)
                live.append(2)
                assert await view.evaluate_async("Promise.resolve(data)", copy=True) == [1, 2]
                observed = []

                async def edit(value):
                    await asyncio.sleep(0)
                    observed.append(value)
                    value.append(3)
                    return value

                view.bind_function("edit", edit)
                assert await view.evaluate_async("edit(data).then(x=>x===data)")
                assert observed[0] is live and live == [1, 2, 3]

                async def step(*, render=False):
                    runtime.update()
                    if render:
                        runtime.refresh_display()
                        runtime.render()
                    await asyncio.sleep(0)

                async with ScriptDriver(runtime, step=step) as driver:
                    result = await driver.page(view).evaluate("Promise.resolve(data)", copy=True)
                    assert type(result) is list and result == [1, 2, 3]

    asyncio.run(run())


if __name__ == "__main__":
    globals()[sys.argv[1]]()
