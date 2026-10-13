"""Native Session acceptance; each invocation owns a fresh Renderer."""

import asyncio
import gc
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from cases import pump, raises

from ultralight_py import ErrorCode, Runtime, UltralightError
from ultralight_py.integrations.asyncio import install


def page(rt, session=None, url="http://session.test/"):
    view = rt.create_view(16, 16, session=session)
    view.load_html("<body>session", url=url)
    pump(rt, lambda: view.is_ready)
    return view


def lifecycle():
    callback_checks = []

    def loader(path):
        if path == "session.html":
            for action in (
                lambda: rt._native.create_session("callback", False),
                lambda: rt._native.check(),
                lambda: session._native.close(True),
            ):
                callback_checks.append(raises(UltralightError, action, ErrorCode.Busy))
            return b"<body>resource"
        return None

    rt = Runtime(cache_path="session-cache", resource_loader=loader)
    for name in ("", "default", "CON", "con", "com1", "lpt9", "a/b", "a.b", "a" * 81, "中文"):
        raises(ValueError, lambda name=name: rt.create_session(name))
    for name in (None, 1, b"a"):
        raises(TypeError, lambda name=name: rt.get_session(name))
    for flag in (None, 0, "yes"):
        raises(TypeError, lambda flag=flag: rt.create_session("a", persistent=flag))
        raises(TypeError, lambda flag=flag: rt.get_or_create_session("a", persistent=flag))
    assert rt.get_session("missing") is None
    session = rt.create_session("account-a")
    assert session.name == "account-a" and not session.persistent
    assert session.disk_path is None and not session.closed
    assert rt.get_session("account-a") is session
    assert rt.get_or_create_session("account-a") is session
    raises(ValueError, lambda: rt.create_session("account-a"))
    raises(ValueError, lambda: rt.get_or_create_session("account-a", persistent=True))
    for flag in (1, None):
        raises(TypeError, lambda flag=flag: session.close(force_close=flag))
    for attr in ("name", "persistent", "disk_path", "closed"):
        raises(AttributeError, lambda attr=attr: setattr(session, attr, None))
    foreign = object.__new__(Runtime)
    raises(
        UltralightError,
        lambda: foreign.create_view(16, 16, session=session),
        ErrorCode.CrossContext,
    )
    left, right = page(rt, session), page(rt, session)
    left.load_url("file:///session.html")
    pump(rt, lambda: left.is_ready)
    assert len(callback_checks) >= 3 and len(callback_checks) % 3 == 0
    default = page(rt)
    assert left.session is session and default.session is None
    raises(AttributeError, lambda: setattr(left, "session", None))
    raises(TypeError, lambda: rt.create_view(16, 16, session="account-a"))
    raises(UltralightError, session.close, ErrorCode.Busy)
    assert not session.closed and left.evaluate("21*2") == 42
    errors = []

    def worker():
        for action in (
            lambda: rt.create_session("worker"),
            lambda: rt.get_session("account-a"),
            session.close,
        ):
            errors.append(raises(UltralightError, action, ErrorCode.WrongThread))

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join()
    assert len(errors) == 3
    handle = left.evaluate_handle("({answer:42})")
    binding = left.bind_function("answer", lambda: 42)
    subscription = left.on("dom_ready", lambda event: None)
    session.close(force_close=True)
    assert session.closed and left.closed and right.closed and not default.closed
    assert subscription.closed and binding.closed
    raises(UltralightError, handle.to_python)
    raises(UltralightError, lambda: rt.create_view(16, 16, session=session), ErrorCode.Closed)
    session.close()
    assert session.name == "account-a" and rt.get_session("account-a") is None
    replacement = rt.create_session("account-a")
    view = page(rt, replacement)
    view.evaluate("localStorage.setItem('discarded','yes')")
    view.close()
    assert not replacement.closed
    page(rt, replacement).close()
    # A View whose Python wrapper disappeared still counts until deferred cleanup.
    forgotten = page(rt, replacement)
    del forgotten
    gc.collect()
    raises(UltralightError, replacement.close, ErrorCode.Busy)
    replacement.close()
    with rt.create_session("context") as context:
        page(rt, context).close()
    assert context.closed
    assert (
        page(rt, rt.create_session("account-a")).evaluate("localStorage.getItem('discarded')")
        is None
    )
    persistent = rt.create_session("saved", persistent=True)
    assert persistent.disk_path == Path("session-cache/saved").resolve()
    saved_view = page(rt, persistent)
    saved_view.evaluate("localStorage.setItem('saved','retained')")
    saved_view.close()
    disk_path = persistent.disk_path
    persistent.close()
    persistent = rt.create_session("saved", persistent=True)
    assert persistent.disk_path == disk_path
    assert page(rt, persistent).evaluate("localStorage.getItem('saved')") == "retained"
    rt.close()
    assert persistent.closed and default.closed
    persistent.close()
    raises(UltralightError, lambda: rt.get_session("saved"), ErrorCode.Closed)


async def database(view, write=False):
    # One origin and database name across every View and Session.
    return await view.evaluate_async(
        """new Promise((resolve,reject)=>{
      const request=indexedDB.open('session-test',1);
      request.onupgradeneeded=()=>request.result.createObjectStore('values');
      request.onerror=()=>reject(request.error);
      request.onsuccess=()=>{
        const db=request.result;
        const tx=db.transaction('values', 'readwrite');
        const store=tx.objectStore('values');
        const op=WRITE ? store.put('stored','key') : store.get('key');
        let result=null;
        op.onsuccess=()=>{result=op.result === undefined ? null : op.result};
        tx.oncomplete=()=>{db.close();resolve(result)};
        tx.onerror=()=>{db.close();reject(tx.error)};
      };
    })""".replace("WRITE", "true" if write else "false")
    )


async def storage(mode):
    cache_hits = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/cached.js":
                cache_hits.append(self.path)
                self.send_response(200)
                self.send_header("Content-Type", "application/javascript")
                self.send_header("Cache-Control", "max-age=86400")
                self.end_headers()
                self.wfile.write(b"window.cachedResource = true;")
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<body>session")

        def log_message(self, *args):
            pass

    port_file = Path("origin-port")
    port = int(port_file.read_text()) if mode == "read" else 0
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    # Persist the port so both subprocesses use exactly the same HTTP origin.
    if mode != "read":
        port_file.write_text(str(server.server_port))
    rt = Runtime(cache_path="session-cache")
    driver = install(rt)
    try:
        a = rt.create_session("a", persistent=True)
        b = rt.create_session("b", persistent=True)
        temp = rt.create_session("temp")

        async def open_page(session):
            view = rt.create_view(16, 16, session=session)
            view.load_url(f"http://127.0.0.1:{server.server_port}/")
            await view.wait_ready()
            return view

        first, shared, isolated, temporary = [await open_page(s) for s in (a, a, b, temp)]
        if mode != "read":
            first.evaluate(
                "document.cookie='account=a; Max-Age=86400; Path=/'; localStorage.setItem('account','a'); sessionStorage.setItem('tab','first')"
            )
            await database(first, True)
            temporary.evaluate(
                "document.cookie='account=temp; Max-Age=86400; Path=/'; localStorage.setItem('account','temp')"
            )
            await database(temporary, True)
        for view in (first, shared):
            assert view.evaluate("document.cookie") == "account=a"
            assert view.evaluate("localStorage.getItem('account')") == "a"
            assert await database(view) == "stored"
        assert shared.evaluate("sessionStorage.getItem('tab')") is None
        assert first.evaluate("sessionStorage.getItem('tab')") == (
            None if mode == "read" else "first"
        )
        for view in (isolated, temporary) if mode == "read" else (isolated,):
            assert view.evaluate("document.cookie") == ""
            assert view.evaluate("localStorage.getItem('account')") is None
            assert await database(view) is None
        if mode != "read":
            temp.close(force_close=True)
            temporary = await open_page(rt.create_session("temp"))
            assert temporary.evaluate("document.cookie") == ""
            assert temporary.evaluate("localStorage.getItem('account')") is None
            assert await database(temporary) is None
        assert not Path("session-cache/temp").exists()
        if mode != "read":

            async def cached_page(session):
                view = rt.create_view(16, 16, session=session)
                view.load_html(
                    '<script src="/cached.js"></script>',
                    url=f"http://127.0.0.1:{server.server_port}/cache-page",
                )
                await view.wait_ready()
                assert view.evaluate("cachedResource") is True
                view.close()

            await cached_page(a)
            assert len(cache_hits) == 1
            await cached_page(a)
            assert len(cache_hits) == 1
            await cached_page(b)
            assert len(cache_hits) == 2

        # Waiting and bridge work must be stopped only for the affected Session.
        started, cancelled = asyncio.Event(), asyncio.Event()

        async def bridge():
            started.set()
            try:
                await asyncio.Future()
            finally:
                cancelled.set()

        first.bind_function("pendingBridge", bridge)
        first.evaluate("void pendingBridge().catch(()=>{})")
        await started.wait()
        pending = asyncio.create_task(shared.wait_until(lambda: False))
        promise = asyncio.create_task(first.evaluate_async("new Promise(()=>{})"))
        await asyncio.sleep(0)
        a.close(force_close=True)
        for task in (pending, promise):
            try:
                await task
            except UltralightError:
                pass
            else:
                raise AssertionError("Session close did not abort pending work")
        await asyncio.wait_for(cancelled.wait(), 2)
        assert not isolated.closed
    finally:
        rt.close()
        driver.close()
        server.shutdown()
        server.server_close()
        thread.join()


if __name__ == "__main__":
    if sys.argv[1] == "lifecycle":
        lifecycle()
    else:
        asyncio.run(storage(sys.argv[1]))
