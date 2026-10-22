# Getting started

Install ultralight-py to create a native window, or execute scripts and capture pixels in an offscreen page.

## Installation

Requires Python 3.10+. Release wheels bundle Ultralight libraries and runtime resources; no separate SDK installation is needed.

```sh
python -m pip install ultralight-py
```

CI targets Windows x64, Linux x64 (glibc ≥ 2.34), and macOS ARM64 (11.3+).
Available platforms depend on the release files. For source installation, see the [Development guide](../../docs/en/development.md).

Optional image dependencies:

```sh
python -m pip install 'ultralight-py[pillow,numpy]'
```

## Creating a native window

Save this code as `hello.py` and run `python hello.py`.
`API` installs registered functions before the first page script; `Application` handles the window and event loop.

```python
from ultralight_py import API, Application

with API("app") as api, Application() as app:

    @api.register
    def hello(name):
        return f"Hello, {name}!"

    window = app.create_window(800, 520, title="Hello, ultralight-py")
    api.attach(window.view)
    window.view.load_html("""
        <style>
          body { background: #111315; color: #edb584;
                 font: 24px system-ui; padding: 48px; }
        </style>
        <h1 id="hello"></h1>
        <script>
          document.querySelector('#hello').textContent = app.hello('world');
        </script>
    """)
    app.run()
```

Create `Application` before the first `Runtime`. Engine operations run on Python's main thread,
and the engine cannot be recreated in the current process after shutdown.
AppCore handles system fonts, IME, and DPI. See [Native windows and the API registry](../../docs/en/appcore.md).

## Offscreen rendering

Without a window, use `Runtime` to create a CPU offscreen View.
Standalone scripts can explicitly select `ScriptDriver.auto()` to advance loading/rendering while waiting.

```python
import asyncio
from ultralight_py import Runtime
from ultralight_py.scripting import ScriptDriver


async def capture(runtime):
    with runtime.create_view(320, 180) as view:
        async with ScriptDriver.auto(runtime) as driver:
            await driver.page(view).load_html(
                "<style>body{background:#ff0000}</style><body>Hello",
                wait_until="settled",
                timeout=5,
            )
        print(view.evaluate("document.body.textContent"))
        frame = view.copy_pixels()
        print(frame.width, frame.height, frame.format)


with Runtime() as runtime:
    asyncio.run(capture(runtime))
```

Pixels use premultiplied-alpha BGRA8. `frame.to_rgba()` returns an independent RGBA image.
For Pillow, NumPy, and row strides, see [Pixels](../../docs/en/guide.md#pixels).
Passive waits such as `View.wait_ready()` do not advance the engine themselves; an existing GUI loop must drive it.

## Next steps

| Goal | Read |
| --- | --- |
| Find methods, parameters, and return values | [Public API](../../docs/en/api.md) |
| Create windows, register functions, or use asyncio | [Native windows and API registry](../../docs/en/appcore.md) |
| Share Python/JavaScript objects bidirectionally | [Object bridging](../../docs/en/objects.md) |
| Customize resources or handle events/input | [User guide](../../docs/en/guide.md) |
| Explore complete applications, recordings, and source | [ultralight-py Showcase](https://shabbywu.github.io/ultralight-py-showcase/en/) |
