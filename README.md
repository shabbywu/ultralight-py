# ultralight-py

English · [简体中文](README.zh-CN.md)

Python bindings for Ultralight 2.x, supporting offscreen rendering, native AppCore windows, and shared functions and objects between Python and JavaScript.

- **Native windows**: AppCore system fonts, DPI, input and IME, sharing an asyncio loop. See the [window guide](docs/appcore.md).
- **Standalone API registry**: decorator-based function registration, exported objects, attachment before loading, and restoration after navigation.
- **Offscreen rendering**: load HTML or web pages, execute JavaScript, and read CPU pixel frames.
- **Session isolation**: views in the same session share browser storage, while separate sessions stay isolated. Temporary and persistent storage are supported; see the [example](examples/sessions.py).
- **Bidirectional bridge**: Python functions, objects and live container proxies, with Promise / asyncio support.
- **Page interaction**: page events and waits, mouse and keyboard input, custom resource loading, and an optional Tkinter input adapter.

## Installation

Requires Python 3.10+.

```sh
python -m pip install ultralight-py
```

Release wheels include the Ultralight shared libraries and runtime resources; no separate SDK installation is required.
CI targets Windows x64, Linux x64 (glibc ≥ 2.34), and macOS ARM64 (11.3+).
Available wheels depend on the release. For installation from source, see the [development guide](https://github.com/shabbywu/ultralight-py/blob/main/docs/development.md).

## Quick start

Load HTML, execute JavaScript, and read the rendered pixels:

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

Engine operations run on Python's main thread. This example uses `ScriptDriver.auto()` to advance the page;
when integrating with an existing GUI or host loop, you can drive the Runtime yourself. Pixels use BGRA8 with premultiplied alpha.
`frame.to_rgba()` returns an independent RGBA image; optional Pillow/NumPy output is covered in the [pixel guide](docs/guide.md#像素).

## Game demo

[Emberkeep](https://github.com/shabbywu/emberkeep) is a desktop pixel roguelike built with ultralight-py 0.5.0. It includes turn-based combat, randomly generated dungeons, upgrades, save continuation, and English and Chinese interfaces.

Python owns the game rules; JavaScript Canvas draws the game and UI. Registered functions, live object proxies, and Promises connect them. The game demonstrates native AppCore windows, an asyncio loop, custom resource loading, and object bridging in a complete application.

See the [Emberkeep README](https://github.com/shabbywu/emberkeep/blob/main/README.md) for setup, controls, and downloads.

## Documentation and examples

The detailed guides below are currently in Chinese.

- [User guide](https://github.com/shabbywu/ultralight-py/blob/main/docs/guide.md): page events, bridging, resource loading, pixels, and input.
- [Public API](https://github.com/shabbywu/ultralight-py/blob/main/docs/api.md) · [Object bridging](https://github.com/shabbywu/ultralight-py/blob/main/docs/objects.md).
- [Examples](https://github.com/shabbywu/ultralight-py/tree/main/examples): offscreen rendering, bidirectional bridging, virtual resources, asyncio, and Tkinter.
- [Development guide](https://github.com/shabbywu/ultralight-py/blob/main/docs/development.md) · [Architecture](https://github.com/shabbywu/ultralight-py/blob/main/docs/architecture.md) · [Release guide](https://github.com/shabbywu/ultralight-py/blob/main/docs/releasing.md).
- [Changelog](https://github.com/shabbywu/ultralight-py/blob/main/CHANGELOG.md).
