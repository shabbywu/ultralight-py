"""Each case runs in a new process: the SDK cannot recreate its Renderer."""

import gc
import sys
import threading
import time
import weakref
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from socketserver import TCPServer

from ultralight_py import (
    ErrorCode,
    JavaScriptError,
    Resource,
    Runtime,
    UltralightError,
    undefined,
)


def raises(kind, function, code=None):
    try:
        function()
    except kind as error:
        if code is not None:
            assert error.code == code, error
        return error
    raise AssertionError(f"Expected {kind.__name__}")


def pump(runtime, predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() >= deadline:
            raise AssertionError("Page operation timed out")
        runtime.update()
        runtime.refresh_display()
        runtime.render()
        time.sleep(0.005)


def load(runtime, view, html, window_ready=None):
    ready, failed = [], []
    view.set_callbacks(
        dom_ready=lambda e: ready.append(e) if e.is_main_frame else None,
        fail_loading=failed.append,
        window_ready=window_ready,
    )
    view.load_html(html)
    pump(runtime, lambda: ready or failed)
    assert not failed, failed


def pixels():
    with Runtime() as runtime:
        with runtime.create_view(80, 60) as view:
            load(runtime, view, "<style>html,body{margin:0;background:#ff0000}</style><body>")
            runtime.update()
            runtime.refresh_display()
            runtime.render()
            frame = view.copy_pixels()
            assert (frame.width, frame.height) == (80, 60)
            assert frame.row_bytes >= frame.width * 4
            assert frame.format == "BGRA8Premultiplied"
            offset = frame.row_bytes * 30 + 40 * 4
            assert frame.data[offset : offset + 4] == bytes([0, 0, 255, 255])
            assert view.evaluate("document.body.tagName") == "BODY"
            view.clear_dirty_bounds()
            assert view.copy_pixels().dirty_bounds == (0, 0, 0, 0)
            view.resize(16, 20)
            runtime.update()
            runtime.refresh_display()
            runtime.render()
            assert view.copy_pixels().width == 16
        assert len(frame.data) >= 80 * 60 * 4
        view.close()
    runtime.close()
    raises(UltralightError, lambda: Runtime(), ErrorCode.Closed)


def transparent():
    with Runtime() as runtime:
        view = runtime.create_view(20, 20, transparent=True)
        load(runtime, view, "<style>html,body{margin:0;background:rgba(255,0,0,0.5)}</style><body>")
        frame = view.copy_pixels()
        pixel = frame.data[frame.row_bytes * 10 + 40 : frame.row_bytes * 10 + 44]
        assert pixel[0] == pixel[1] == 0
        assert pixel[2] == pixel[3] and 120 <= pixel[3] <= 200, pixel


def values():
    with Runtime() as runtime:
        view = runtime.create_view(16, 16)
        load(runtime, view, "<body>")
        assert view.evaluate("null") is None
        assert view.evaluate("undefined") is undefined
        assert view.evaluate("true") is True
        assert view.evaluate('"中文\\u0000😀"') == "中文\0😀"
        assert view.evaluate("[,1,,]") == [undefined, 1, undefined]
        echo = view.evaluate_handle("x => x")
        value = {"中文\0": [None, undefined, True, 1, 1.25, "😀\0"], "__proto__": 5}
        assert echo.call(value).to_python() == value
        assert echo.call(9007199254740991).to_python() == 9007199254740991
        raises(OverflowError, lambda: echo.call(9007199254740992))
        raises(OverflowError, lambda: echo.call(10**100))
        mapping = {1: "supported"}
        assert echo.call(mapping).to_python() is mapping
        cycle = []
        cycle.append(cycle)
        assert echo.call(cycle).to_python() is cycle
        raises(
            UltralightError,
            lambda: view.evaluate("let cycle={}; cycle.self=cycle; cycle"),
            ErrorCode.TraversalLimit,
        )
        nested = []
        for _ in range(65):
            nested = [nested]
        assert echo.call(nested).to_python() is nested
        raises(TypeError, lambda: view.evaluate("new Date()"))
        raises(TypeError, lambda: view.evaluate("() => 1"))
        assert view.evaluate("({a:[{b:2},{b:2}]})") == {"a": [{"b": 2}, {"b": 2}]}


def handles():
    with Runtime() as runtime:
        view = runtime.create_view(16, 16)
        load(runtime, view, "<body>")
        obj = view.evaluate_handle("({value:3, add(n){return this.value+n}})")
        obj.set("value", 7)
        obj.set("中文\0😀", "value\0tail")
        assert obj.get("中文\0😀").to_python() == "value\0tail"
        assert obj.get("value").to_python() == 7
        assert obj.keys() == ["value", "add", "中文\0😀"]
        fn = obj.get("add")
        assert fn.call(2, this=obj).to_python() == 9
        array = view.evaluate_handle("[1,2]")
        array.set(1, 8)
        assert array.get(1).to_python() == 8
        second = runtime.create_view(16, 16)
        load(runtime, second, "<body>")
        other = second.evaluate_handle("({x:1})")
        raises(UltralightError, lambda: obj.set("other", other), ErrorCode.CrossContext)
        raises(UltralightError, lambda: fn.call(1, this=other), ErrorCode.CrossContext)
        load(runtime, view, "<body>new document")
        raises(UltralightError, obj.to_python, ErrorCode.PageGone)
        obj.close()
        obj.close()
        second.close()
        raises(UltralightError, other.to_python, ErrorCode.PageGone)


def callbacks():
    with Runtime() as runtime:
        view = runtime.create_view(16, 16)
        events, console = [], []

        def ready(event):
            events.append(event)
            if event.is_main_frame:
                view.bind_function("echo\0中文", lambda value: value)
                view.bind_function("plus", lambda a, b: a + b)

        view.set_callbacks(
            window_ready=ready, console=console.append, dom_ready=lambda e: events.append(e)
        )
        view.load_html('<script>window.answer=plus(2,3);console.log("saved message")</script>')
        pump(runtime, lambda: view.evaluate("typeof answer !== 'undefined'"))
        assert view.evaluate("answer") == 5
        assert view.evaluate('window["echo\\u0000中文"]("中文")') == "中文"
        assert console[0]["message"] == "saved message"
        retained = events[0]
        load(runtime, view, "<body>")
        assert view.evaluate("typeof plus") == "undefined"
        assert retained.is_main_frame
        assert console[0]["message"] == "saved message"


def errors():
    with Runtime() as runtime:
        reported = []
        runtime.set_error_handler(reported.append)
        view = runtime.create_view(16, 16)
        load(runtime, view, "<body>")
        error = raises(JavaScriptError, lambda: view.evaluate('throw new Error("js failure")'))
        assert error.code == ErrorCode.ScriptException and "js failure" in str(error)
        assert error.stack

        def fail():
            raise ValueError("python failure")

        view.bind_function("fail", fail)
        raises(JavaScriptError, lambda: view.evaluate("fail()"))

        def event_fail(event):
            raise ValueError("event failure")

        view.set_callbacks(dom_ready=event_fail)
        view.load_html("<body>")
        pump(runtime, lambda: reported)
        assert reported[0].code == ErrorCode.HostException and "event failure" in str(reported[0])
        unraisable = []
        sys.unraisablehook = unraisable.append
        runtime.set_error_handler(None)
        view.load_html("<body>")
        pump(runtime, lambda: unraisable)
        assert "event failure" in str(unraisable[0].exc_value)
        runtime.set_error_handler(lambda error: fail())
        view.load_html("<body>")
        pump(runtime, lambda: len(unraisable) > 1)
        assert "python failure" in str(unraisable[-1].exc_value)


def lifecycle():
    class Callback:
        def __call__(self, *args):
            return "ok"

    with Runtime() as runtime:
        assert Runtime() is runtime
        raises(ValueError, lambda: Runtime(assets_root="different"))
        view = runtime.create_view(16, 16)
        load(runtime, view, "<body>")
        callback = Callback()
        weak = weakref.ref(callback)
        view.set_callbacks(console=callback)
        del callback
        assert weak() is not None
        view.set_callbacks()
        gc.collect()
        assert weak() is None
        callback = Callback()
        weak = weakref.ref(callback)
        view.bind_function("callback", callback)
        del callback
        assert weak() is not None
        load(runtime, view, "<body>")
        gc.collect()
        assert weak() is None
        callback = Callback()
        weak = weakref.ref(callback)
        view.bind_function("callback", callback)
        del callback
        view.close()
        gc.collect()
        assert weak() is None
        raises(UltralightError, lambda: view.load_html("x"), ErrorCode.Closed)
        view.close()
        other = runtime.create_view(16, 16)
        native = other._native
        holder = [other]
        del other
        thread = threading.Thread(target=lambda: holder.clear())
        thread.start()
        thread.join()
        runtime.update()
        assert native.closed


def threading_case():
    with Runtime() as runtime:
        view = runtime.create_view(16, 16)
        load(runtime, view, "<body>")
        value = view.evaluate_handle("({x:1})")
        failures = []

        def worker():
            for operation in [Runtime, runtime.update, runtime.close, view.close, value.to_python]:
                failures.append(raises(UltralightError, operation, ErrorCode.WrongThread))

        thread = threading.Thread(target=worker)
        thread.start()
        thread.join(2)
        assert not thread.is_alive() and len(failures) == 5


def reentrant():
    with Runtime() as runtime:
        view = runtime.create_view(16, 16)
        failures = []

        def ready(event):
            if event.is_main_frame:
                failures.append(raises(UltralightError, runtime.update, ErrorCode.Busy))

        load(runtime, view, "<body><script>1</script>", ready)
        assert failures
        view.set_callbacks(dom_ready=lambda e: view.close() if e.is_main_frame else None)
        view.load_html("<body>")
        pump(runtime, lambda: view.closed)
        other = runtime.create_view(16, 16)
        load(runtime, other, "<body>")
        other.bind_function("navigate", lambda: other.load_html("<body>next"))
        raises(UltralightError, lambda: other.evaluate("navigate()"), ErrorCode.PageGone)


def resources():
    calls, failures = [], []
    root = Path.cwd()
    (root / "disk.js").write_text("window.fromDisk=11", encoding="utf-8")
    content = {
        "page.html": Resource(
            b'<script src="virtual.js"></script><script src="disk.js"></script><body>virtual',
            "text/html",
        ),
        "virtual.js": b"window.fromPython=42",
        "empty.js": b"",
    }
    active_runtime = None

    def loader(path):
        calls.append((path, threading.get_ident()))
        if active_runtime is not None:
            failures.append(raises(UltralightError, active_runtime.update))
        return content.get(path)

    with Runtime(assets_root=root, resource_loader=loader) as runtime:
        active_runtime = runtime
        view = runtime.create_view(16, 16)
        ready, failed = [], []
        view.set_callbacks(
            dom_ready=lambda e: ready.append(e) if e.is_main_frame else None,
            fail_loading=failed.append,
        )
        view.load_url("file:///page.html")
        pump(runtime, lambda: ready or failed)
        assert not failed, failed
        assert view.evaluate("fromPython + fromDisk") == 53
        assert calls and failures
        assert any(thread != threading.get_ident() for _, thread in calls)
        assert not any("icudt" in path or "cacert" in path for path, _ in calls)
        load(
            runtime,
            view,
            '<script src="file:///empty.js"></script><script>window.afterEmpty=1</script>',
        )
        assert view.evaluate("afterEmpty") == 1


def resource_errors():
    started, finished = threading.Event(), threading.Event()
    closing, release = threading.Event(), threading.Event()

    class Loader:
        def __call__(self, path):
            if path == "bad.html":
                raise ValueError("resource failure")
            if path == "slow.html":
                if threading.current_thread() is not threading.main_thread():
                    started.set()
                    assert release.wait(2), "Close did not release the waiting resource callback"
                    finished.set()
                return b"<body>slow"
            return None

    loader = Loader()
    weak = weakref.ref(loader)
    runtime = Runtime(resource_loader=loader)
    del loader
    errors, failed = [], []
    runtime.set_error_handler(errors.append)
    view = runtime.create_view(16, 16)
    view.set_callbacks(fail_loading=failed.append)
    view.load_url("file:///bad.html")
    pump(runtime, lambda: errors and failed)
    assert "resource failure" in str(errors[0])
    if sys.platform != "win32":
        blocked = Path.cwd() / "blocked"
        # A symlink loop makes filesystem lookup fail even when tests run as
        # root in manylinux containers; chmod(0) does not restrict root.
        blocked.symlink_to(blocked.name, target_is_directory=True)
        errors.clear()
        failed.clear()
        try:
            view.load_url("file:///blocked/page.html")
            pump(runtime, lambda: errors and failed)
            assert errors[0].code == ErrorCode.HostException
        finally:
            blocked.unlink()
    view.load_url("file:///slow.html")

    def unblock():
        assert closing.wait(3)
        time.sleep(0.03)
        release.set()

    thread = threading.Thread(target=unblock, daemon=True)
    thread.start()
    pump(runtime, started.is_set)
    assert not finished.is_set()
    closing.set()
    runtime.close()
    gc.collect()
    thread.join(2)
    assert finished.is_set()
    assert weak() is None


def http():
    class LoopbackServer(ThreadingHTTPServer):
        def server_bind(self):
            # HTTPServer normally performs reverse DNS during bind. This local
            # fixture should not depend on the runner's DNS/network settings.
            TCPServer.server_bind(self)
            self.server_name = "localhost"
            self.server_port = self.server_address[1]

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            data = b"<body><script>window.networkAnswer=123</script>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    server = LoopbackServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with Runtime() as runtime:
            view = runtime.create_view(16, 16)
            ready, failed = [], []
            view.set_callbacks(
                dom_ready=lambda e: ready.append(e) if e.is_main_frame else None,
                fail_loading=failed.append,
            )
            view.load_url(f"http://127.0.0.1:{server.server_port}/page")
            pump(runtime, lambda: ready or failed)
            assert not failed, failed
            assert view.evaluate("networkAnswer") == 123
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)


def cache_path():
    raises(TypeError, lambda: Runtime(cache_path=123))
    raises(ValueError, lambda: Runtime(cache_path="bad\0path"))
    directory = Path("browser-cache").resolve()
    with Runtime(cache_path=Path("browser-cache")) as runtime:
        assert Runtime() is runtime
        assert Runtime(cache_path=str(directory)) is runtime
        raises(ValueError, lambda: Runtime(cache_path="other-cache"))
        view = runtime.create_view(16, 16)
        load(runtime, view, "<body>cache")
        assert not Path("default").exists()


def cache_storage():
    with Runtime(cache_path="persistent-cache") as runtime:
        view = runtime.create_view(16, 16)
        ready = []
        view.set_callbacks(dom_ready=lambda e: ready.append(e) if e.is_main_frame else None)
        view.load_html("<body>storage", url="http://cache.test/")
        pump(runtime, lambda: ready)
        if sys.argv[1] == "cache_write":
            view.evaluate("localStorage.setItem('persisted', 'from-first-process')")
        else:
            assert view.evaluate("localStorage.getItem('persisted')") == "from-first-process"
    assert Path("persistent-cache/default").is_dir()
    assert not Path("default").exists()


def exit_cleanup():
    runtime = Runtime(resource_loader=lambda path: None)
    view = runtime.create_view(16, 16)
    view.bind_function("cycle", lambda: view)
    value = view.evaluate_handle("({heldUntilExit:true})")
    assert not value.closed
    view.load_url("file:///missing.html")
    runtime.update()
    # Deliberately rely on atexit, with retained native and Python references.


CASES = {
    "cache_path": cache_path,
    "cache_write": cache_storage,
    "cache_read": cache_storage,
    "pixels": pixels,
    "transparent": transparent,
    "values": values,
    "handles": handles,
    "callbacks": callbacks,
    "errors": errors,
    "lifecycle": lifecycle,
    "threading": threading_case,
    "reentrant": reentrant,
    "resources": resources,
    "resource_errors": resource_errors,
    "http": http,
    "exit_cleanup": exit_cleanup,
}

if __name__ == "__main__":
    CASES[sys.argv[1]]()
