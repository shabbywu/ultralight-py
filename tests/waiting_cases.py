"""Real Renderer acceptance, one process per case (the Renderer cannot restart)."""

import asyncio
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from ultralight_py import ErrorCode, JavaScriptError, PageLoadError, Runtime, UltralightError
from ultralight_py.scripting import ScriptDriver


async def automatic(runtime):
    view = runtime.create_view(32, 32)
    callbacks, urls, errors = [], [], []
    runtime.set_error_handler(errors.append)

    def broken(event):
        if event.is_main_frame:
            raise ValueError("isolated callback")

    view.set_callbacks(dom_ready=broken, page_settled=urls.append)
    view.on("dom_ready", lambda event: callbacks.append(event))
    async with ScriptDriver.auto(runtime) as driver:
        page = driver.page(view)
        await page.load_html(
            "<style>html,body{margin:0;background:#ff0000}</style><body>"
            '<iframe srcdoc="<body>child</body>"></iframe>',
            wait_until="settled",
            timeout=5,
        )
        assert view.is_ready and view.is_settled and urls
        assert any(event.is_main_frame for event in callbacks)
        assert any(error.code == ErrorCode.HostException for error in errors)
        assert len(view.copy_pixels().data) >= 32 * 32 * 4
        view.set_callbacks()
        await page.evaluate(
            'setTimeout(() => {const e=document.createElement("div");'
            'e.id="late";document.body.appendChild(e)}, 20)'
        )
        assert await page.wait_for_selector("#late")
        assert await page.evaluate("new Promise(r => setTimeout(() => r(42), 20))") == 42
        assert await page.evaluate("new Promise(r => requestAnimationFrame(() => r(7)))") == 7
        await page.evaluate(
            'requestAnimationFrame(() => {const e=document.createElement("div");'
            'e.id="raf";document.body.appendChild(e)})'
        )
        assert await page.wait_for_selector("#raf", render=True)
        try:
            await page.evaluate('Promise.reject(new Error("expected"))')
        except JavaScriptError as error:
            assert "expected" in str(error)
        else:
            raise AssertionError("Promise rejection lost")
        try:
            await page.wait_for_selector("[")
        except JavaScriptError:
            pass
        else:
            raise AssertionError("Invalid selector was swallowed")
        try:
            await page.evaluate("new Promise(() => {})", timeout=0.03)
        except TimeoutError:
            pass
        else:
            raise AssertionError("Promise timeout lost")
        assert not runtime._async_work - {driver.close}
    assert not view.closed and not runtime.closed


async def manual(runtime):
    view = runtime.create_view(16, 16)
    calls = []
    update = runtime.update

    def counted_update():
        calls.append("update")
        update()

    runtime.update = counted_update
    view.load_html("<body>passive")
    waiting = asyncio.create_task(view.wait_ready())
    await asyncio.sleep(0.02)
    assert not calls
    while not waiting.done():
        runtime.update()
        await asyncio.sleep(0.002)
    await waiting
    waiting = asyncio.create_task(view.wait_settled())
    while not waiting.done():
        runtime.update()
        runtime.refresh_display()
        runtime.render()
        await asyncio.sleep(0.002)
    await waiting
    assert view.is_settled
    old = asyncio.create_task(view.wait_until(lambda: False))
    await asyncio.sleep(0)
    view.load_html("<body>replacement")
    try:
        await old
    except UltralightError as error:
        assert error.code == ErrorCode.PageGone
    else:
        raise AssertionError("Replaced-document wait survived")
    waiting = asyncio.create_task(view.wait_ready())
    await asyncio.sleep(0)
    view.close()
    try:
        await waiting
    except UltralightError as error:
        assert error.code == ErrorCode.Closed
    else:
        raise AssertionError("Closed View left a waiter")


async def http(runtime):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if urlsplit(self.path).path == "/redirect":
                self.send_response(302)
                self.send_header("Location", "/final")
                self.send_header("Content-Length", "0")
                self.end_headers()
            else:
                body = b"<body><div id='final'>ready</div></body>"
                self.send_response(404 if self.path == "/missing" else 200)
                self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}"
        view = runtime.create_view(16, 16)
        async with ScriptDriver.auto(runtime) as driver:
            page = driver.page(view)
            await page.navigate(url + "/redirect", wait_until="settled", timeout=5)
            assert view.evaluate("location.pathname") == "/final"
            assert await page.wait_for_selector("#final")
            for _ in range(2):
                await page.navigate(url + "/final")
                assert view.is_ready
            for action, html in (
                ("document.querySelector('a').click()", '<a href="/redirect">go</a>'),
                ("document.querySelector('form').submit()", '<form action="/redirect"></form>'),
            ):
                await page.load_html(html, url + "/actions", timeout=5)
                previous = view.navigation_id
                async with page.expect_navigation(wait_until="settled", timeout=5):
                    view.evaluate(f"setTimeout(() => {{{action}}}, 0)")
                assert view.navigation_id > previous and view.is_settled
                assert view.evaluate("location.pathname") == "/final", view.evaluate(
                    "location.href"
                )
                assert await page.wait_for_selector("#final")
            try:
                await page.navigate(url + "/missing", wait_until="settled", timeout=5)
            except PageLoadError as error:
                assert error.failure.code == 404
            else:
                raise AssertionError("HTTP failure became success")
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


with Runtime() as runtime:
    asyncio.run({"automatic": automatic, "manual": manual, "http": http}[sys.argv[1]](runtime))
