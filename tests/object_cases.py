"""Object bridge cases use fresh processes because Runtime is process-scoped."""

import gc
import sys
import threading
import time
import weakref
from typing import ClassVar

from cases import load, raises

from ultralight_py import ErrorCode, JavaScriptError, Runtime, UltralightError, undefined


class Counter:
    shared: ClassVar[list] = []

    def __init__(self, value=0):
        self.value = value
        self.values = [1, 2]
        self.options = {"keys": 9, 1: "integer"}
        self.child = self
        self.reads = 0
        self._secret = 42

    def increment(self, n=1):
        self.value += n
        return self.value

    def myself(self):
        return self

    @property
    def doubled(self):
        self.reads += 1
        return self.value * 2

    @doubled.setter
    def doubled(self, value):
        self.value = value // 2

    @property
    def readonly(self):
        return 42

    @property
    def broken(self):
        raise ValueError("getter failure")


def instances():
    with Runtime() as runtime:
        view = runtime.create_view(16, 16)
        load(runtime, view, "<body>")
        left, right = Counter(0), Counter(100)
        view.bind_object("left", left)
        view.bind_object("right", right)
        assert view.evaluate("left !== right")
        assert view.evaluate("left.increment(2)") == 2
        assert view.evaluate("right.increment(3)") == 103
        assert view.evaluate("const fn=left.increment; fn.call(right,4)") == 6
        assert (left.value, right.value) == (6, 103)
        assert view.evaluate("left.child===left && left.myself()===left")
        assert view.evaluate("left") is left
        view.evaluate("left.shared.append(7)")
        assert right.shared == [7]
        view.evaluate("left.value=12; left.doubled=30")
        assert left.value == 15 and left.reads == 0
        assert view.evaluate("left.doubled") == 30
        assert left.reads == 1
        keys = view.evaluate("Object.keys(left)")
        assert "value" in keys and "doubled" in keys and "_secret" not in keys
        assert left.reads == 1
        assert view.evaluate("'value' in left && !('_secret' in left)")
        assert view.evaluate("left._secret") is undefined
        for source in [
            "left.readonly=3",
            "left.increment=3",
            "left.unknown=3",
            "left.broken",
            "Python.getattr(left,'_secret')",
        ]:
            raises(JavaScriptError, lambda source=source: view.evaluate(source))
        view.bind_object("limited", left, members=["value"])
        assert view.evaluate("limited.increment") is undefined
        raises(JavaScriptError, lambda: view.evaluate("Python.getattr(limited,'increment')"))
        assert view.evaluate("Object.keys(limited)") == ["value"]

        class Slotted:
            __slots__ = ("value",)

            def __init__(self):
                self.value = 3

        value = Slotted()
        view.bind_object("slotted", value)
        view.evaluate("slotted.value=8")
        assert value.value == 8
        raises(ValueError, lambda: view.bind_object("bad", left, members=["_secret"]))
        raises(TypeError, lambda: view.bind_object("class_object", Counter))

        class ShadowedDict:
            value = 3

            @property
            def __dict__(self):
                raise AssertionError("Enumeration executed __dict__ getter")

        view.bind_object("shadowed", ShadowedDict())
        assert view.evaluate("Object.keys(shadowed)") == ["value"]


def containers():
    with Runtime() as runtime:
        view = runtime.create_view(16, 16)
        load(runtime, view, "<body>")
        assert view.evaluate("Python.len([1,2,3])") == 3
        items = [1, 2, 3]
        mapping = {"keys": 9, 1: "integer"}
        view.bind_object("items", items)
        view.bind_object("mapping", mapping)
        assert view.evaluate("Array.isArray(items)") is False
        assert view.evaluate("items[0]") is undefined
        assert view.evaluate("Python.getitem(items,-1)") == 3
        view.evaluate("Python.setitem(items,-1,7); items.append(8); items.insert(0,0)")
        assert items == [0, 1, 2, 7, 8]
        items[1] = 10
        assert view.evaluate("Python.getitem(items,1)") == 10
        view.evaluate("Python.delitem(items,0)")
        assert items == [10, 2, 7, 8]
        assert view.evaluate("Python.getitem(items,Python.slice(1,null,2))") == [2, 8]
        view.evaluate("Python.setitem(items,Python.slice(0,2),[3,4])")
        assert items == [3, 4, 7, 8]
        assert view.evaluate("Python.contains(items,7) && Python.len(items)===4")
        assert view.evaluate("Python.getitem(mapping,'keys')") == 9
        assert view.evaluate("Python.getitem(mapping,1)") == "integer"
        view.evaluate("mapping.update({enabled:true}); Python.setitem(mapping,'keys',42)")
        assert mapping["keys"] == 42 and mapping["enabled"] is True
        assert view.evaluate("[...Python.iter(mapping.keys())]") == ["keys", 1, "enabled"]
        assert view.evaluate(
            "Python.call(items.sort,[],{reverse:true}); Python.to_value(items)"
        ) == [8, 7, 4, 3]
        view.bind_object("immutable", (1, 2))
        assert view.evaluate("Python.getitem(immutable,-1)") == 2
        for source, message in [
            ("Python.getitem(items,99)", "IndexError"),
            ("Python.getitem(items,1.5)", "TypeError"),
            ("Python.getitem(items,'0')", "TypeError"),
            ("Python.getitem(mapping,'absent')", "KeyError"),
            ("Python.setitem(immutable,0,8)", "TypeError"),
            ("Python.to_value(mapping)", "TypeError"),
        ]:
            assert message in str(
                raises(JavaScriptError, lambda source=source: view.evaluate(source))
            )
        cycle = []
        cycle.append(cycle)
        view.bind_object("cycle", cycle)
        assert view.evaluate("Python.getitem(cycle,0)===cycle")
        raises(JavaScriptError, lambda: view.evaluate("Python.to_value(cycle)"))
        view.evaluate("const it=Python.iter(mapping); it.next(); Python.setitem(mapping,'new',8)")
        assert "RuntimeError" in str(raises(JavaScriptError, lambda: view.evaluate("it.next()")))
        assert view.evaluate("const done=Python.iter([]); done.next().done && done.next().done")


def conversion():
    with Runtime() as runtime:
        view = runtime.create_view(16, 16)
        load(runtime, view, "<body>")
        counter = Counter()
        view.bind_object("counter", counter)
        value = [counter, {1: "one"}]
        view.bind_function("get_data", lambda: value)
        assert view.evaluate("get_data()") is value
        assert view.evaluate("get_data()===get_data()")
        view.evaluate("Python.getitem(get_data(),0).increment(3)")
        assert counter.value == 3
        counter.script = view.evaluate_handle("n=>n*2")
        assert view.evaluate("counter.script(3)") == 6
        view.bind_function("same", lambda item: item is counter)
        assert view.evaluate("same(counter)")
        echo = view.evaluate_handle("x=>x")
        assert echo.call(value).to_python() is value
        obj = view.evaluate_handle("({})")
        obj.set("data", value)
        assert obj.get("data").to_python() is value
        assert view.evaluate("[1,2]") == [1, 2]
        assert isinstance(view.evaluate("2"), int)
        assert isinstance(view.evaluate("2.5"), float)
        view.bind_function("nested", lambda: counter.values)
        assert view.evaluate("nested()") is counter.values
        view.evaluate("nested().append(9)")
        assert counter.values[-1] == 9
        view.bind_function("keyword", lambda *, value: value)
        assert view.evaluate("Python.call(keyword,[],{value:42})") == 42

        # bind_function preserves callable identity and native JSValue conversion.
        class CallableModel:
            def __call__(self):
                return self

        callable_model = CallableModel()
        view.bind_function("callable_model", callable_model)
        assert view.evaluate("callable_model") is callable_model
        assert view.evaluate("callable_model()===callable_model")
        with view.evaluate_handle("({answer:42})") as script:
            binding = view.bind_function("get_script", lambda: script)
            assert view.evaluate("get_script().answer") == 42
            binding.close()

        async def async_value():
            return 1

        view.bind_function("async_value", async_value)
        raises(JavaScriptError, lambda: view.evaluate("async_value()"))


def revocation():
    with Runtime() as runtime:
        view = runtime.create_view(16, 16)
        load(runtime, view, "<body>")
        value = Counter()
        first = view.bind_object("first", value)
        second = view.bind_object("second", value)
        weak = weakref.ref(value)
        assert view.evaluate("first!==second && first.values!==second.values")
        view.evaluate(
            "globalThis.saved=first; globalThis.method=first.increment; globalThis.child=first.values; globalThis.it=Python.iter(child); undefined"
        )
        first.close()
        first.close()
        assert first.closed and not second.closed
        assert view.evaluate("typeof first") == "undefined"
        for source in [
            "saved.value",
            "saved.value=8",
            "method()",
            "child.append(7)",
            "it.next()",
            "Object.keys(saved)",
            "'value' in saved",
        ]:
            raises(JavaScriptError, lambda source=source: view.evaluate(source))
        raises(UltralightError, lambda: view.evaluate("saved"), ErrorCode.PageGone)
        assert view.evaluate("second.increment(2)") == 2
        del value
        assert weak() is not None
        view.unbind("second")
        gc.collect()
        assert second.closed and weak() is None
        view.unbind("missing")
        old = view.bind_object("model", Counter(7))
        view.evaluate("globalThis.old=model")
        raises(TypeError, lambda: view.bind_object("model", Counter))
        assert not old.closed and view.evaluate("model.value") == 7
        replacement = view.bind_object("model", Counter(8))
        assert old.closed and view.evaluate("model.value") == 8
        raises(JavaScriptError, lambda: view.evaluate("old.value"))
        with view.bind_object("context", Counter()) as binding:
            assert not binding.closed
        assert binding.closed
        # The handle is optional; the View retains the binding.
        view.bind_object("kept", Counter(9))
        gc.collect()
        assert view.evaluate("kept.value") == 9
        load(runtime, view, "<body>new")
        assert replacement.closed
        view.bind_object("model", Counter(10))
        # A page replacement of the name must survive closing the old handle.
        overwritten = view.bind_object("overwritten", Counter())
        view.evaluate("overwritten=42")
        overwritten.close()
        assert view.evaluate("overwritten") == 42
        view.close()


def cleanup():
    with Runtime() as runtime:
        view = runtime.create_view(16, 16)
        load(runtime, view, "<body>")
        value = Counter()
        weak = weakref.ref(value)
        handle = view.bind_object("model", value)
        view.evaluate("globalThis.method=model.increment; globalThis.child=model.values")
        del value
        assert weak() is not None
        load(runtime, view, "<body>next")
        gc.collect()
        assert handle.closed and weak() is None
        value = Counter()
        weak = weakref.ref(value)
        handle = view.bind_object("model", value)
        del value
        observed, ready = [], threading.Event()

        def observe():
            ready.set()
            deadline = time.monotonic() + 2
            while not handle.closed:
                if time.monotonic() > deadline:
                    return
                time.sleep(0.001)
            observed.append(True)

        worker = threading.Thread(target=observe)
        worker.start()
        assert ready.wait(2)
        runtime.close()
        gc.collect()
        worker.join(2)
        assert observed == [True] and not worker.is_alive()
        assert handle.closed and weak() is None
        handle.close()


def guards():
    with Runtime() as runtime:
        view = runtime.create_view(16, 16)
        load(runtime, view, "<body>")
        binding = view.bind_object("model", Counter())
        errors = []

        def worker():
            for operation in [
                binding.close,
                lambda: view.bind_object("other", Counter()),
                lambda: view.unbind("model"),
            ]:
                try:
                    operation()
                except UltralightError as error:
                    errors.append(error.code)

        thread = threading.Thread(target=worker)
        thread.start()
        thread.join()
        assert errors == [ErrorCode.WrongThread] * 3

        def nested():
            raises(UltralightError, lambda: view.input_text("x"), ErrorCode.Busy)
            return view.evaluate("model.value")

        view.bind_function("nested", nested)
        assert view.evaluate("nested()") == 0

        def revoke():
            binding.close()
            return 42

        model = Counter()
        model.revoke = revoke
        binding = view.bind_object("model", model)
        view.evaluate("model.revoke()")
        assert binding.closed
        iterator_refs = []

        class Iterator:
            def __iter__(self):
                return self

            def __next__(self):
                raise StopIteration

        class IteratorMaker:
            def __iter__(self):
                binding.close()
                iterator = Iterator()
                iterator_refs.append(weakref.ref(iterator))
                return iterator

        binding = view.bind_object("maker", IteratorMaker())
        view.evaluate("Python.iter(maker); undefined")
        gc.collect()
        assert binding.closed and iterator_refs[0]() is None

        class Closer:
            def close(self):
                view.close()
                return 42

        view.bind_object("closer", Closer())
        raises(UltralightError, lambda: view.evaluate("closer.close()"), ErrorCode.PageGone)
        assert view.closed


CASES = {
    name: globals()[name]
    for name in ["instances", "containers", "conversion", "revocation", "cleanup", "guards"]
}
if __name__ == "__main__":
    CASES[sys.argv[1]]()
