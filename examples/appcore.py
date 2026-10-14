"""Native window, system fonts, IME, Session storage and decorator exports.

Run normally to try typing Chinese, resizing and moving between displays.
--smoke checks the page and async bridge, then closes the native window.
"""

import argparse
import asyncio

from ultralight_py import API, Application, Resource

HTML = """<!doctype html><meta charset="utf-8">
<style>
body { font: 17px system-ui, sans-serif; margin: 32px; color: #182238; background: #f4f6fb; }
input, button { font: inherit; padding: 10px; margin: 8px 0; }
input { display: block; width: 90%; }
.card { background: white; border-radius: 12px; padding: 20px; }
</style>
<h1>Python + AppCore</h1>
<p>系统字体 · 中文 · 日本語 · 한글</p>
<div class="card">
<label>IME <input id="editor" placeholder="输入中文，验证预编辑和候选框"></label>
<button onclick="app.add(1).then(show)">Increment in Python</button>
<button onclick="app.quit().catch(()=>{})">Close</button>
<p id="result"></p><p id="metrics"></p>
</div>
<script>
function show(value) { document.getElementById('result').textContent = 'Python: ' + value; }
globalThis.initial = app.add(0).then(value => { show(value); return value; });
function metrics() {
 document.getElementById('metrics').textContent =
   `${innerWidth} × ${innerHeight} CSS pixels · DPI scale ${devicePixelRatio}`;
}
addEventListener('resize', metrics); metrics();
</script>"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cpu", action="store_true", help="Use CPU rendering")
    parser.add_argument("--smoke", action="store_true", help="Validate and close automatically")
    args = parser.parse_args()
    resources = {"index.html": Resource(HTML.encode(), "text/html")}
    with (
        API("app") as api,
        Application(
            resource_loader=resources.get, force_cpu_renderer=args.cpu, app_name="PythonAppCore"
        ) as app,
    ):
        session = app.runtime.create_session("desktop")
        window = app.create_window(800, 520, title="Python + AppCore", session=session)
        count = 0

        @api.register
        async def add(amount):
            nonlocal count
            await asyncio.sleep(0)
            count += amount
            return count

        @api.register
        async def quit():
            await asyncio.sleep(0)
            window.close()

        api.attach(window.view)
        window.view.load_url("file:///index.html")
        if args.smoke:

            async def verify():
                try:
                    await window.view.wait_settled(timeout=10)
                    assert await window.view.evaluate_async("initial") == 0
                    assert await window.view.evaluate_async("app.add(2)") == 2
                    assert (
                        abs(window.view.evaluate("devicePixelRatio") - window.device_scale) < 0.01
                    )
                    print("AppCore smoke passed", flush=True)
                finally:
                    window.close()

            async def run():
                pump = asyncio.create_task(app.run_async())
                try:
                    await verify()
                finally:
                    app.close()
                    await pump

            asyncio.run(run())
        else:
            app.run()


if __name__ == "__main__":
    main()
