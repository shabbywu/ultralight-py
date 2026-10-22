# User guide

This guide covers page loading, bidirectional bridging, resources, pixels, and input.
For signatures, see the [Public API](api.md); for proxy semantics, see [Object bridging](objects.md).

For AppCore native windows, system fonts, IME, and the standalone API registry, see the [Window guide](appcore.md).

## Minimal offscreen workflow

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
        print(frame.width, frame.height, frame.row_bytes, frame.format)
        view.clear_dirty_bounds()


with Runtime() as runtime:
    asyncio.run(capture(runtime))
```

An existing host loop can use `await view.wait_ready()` / `wait_settled()` directly; they do not advance the engine implicitly.
Use `ScriptDriver(runtime, step=host.request_step)` for the script interface while leaving scheduling to the host.
See [Page waits and subscriptions](api.md#page-waits-and-event-subscriptions) for subscription and navigation-invalidation rules.
For page replacement caused by clicking or submitting, register a wait before the action using `async with page.expect_navigation(...)`.
Wait for selectors on the new page after context exit; the action and navigation share a timeout budget.

Complete examples include loading-error handling:

```sh
python examples/offscreen.py
python examples/bridge.py
python examples/resources.py
python examples/objects.py
python -m pytest tests -q
```

## Runtime, threads, and cleanup

- `Runtime()` returns the process's unique instance; repeated calls share its Renderer. The first call freezes resource configuration.
  Use `Runtime(cache_path="./cache")` to set disk cache and persistent browser storage.
  Explicit directories resolve to absolute paths. `None` keeps SDK defaults; later omitted values reuse the first configuration.
  A different directory or loader supplied later raises an error. `Runtime.close()` closes all Views, after which the Renderer cannot be recreated.
  Normally reuse Runtime and create/close Views as needed. Exiting its context manager closes it.
- Runtime, View, and JSValue operations and explicit closing require Python's main thread.
  An offscreen Runtime does not start a host loop; the host calls `update()`, `refresh_display()`, and `render()`.
  `update()` also processes handle and callback cleanup. Application continuously drives AppCore windows; its Runtime cannot be updated manually.
- View garbage collection only queues a close task, processed by later main-thread calls.
  Use `close()` or `with` for prompt release. `atexit` closes Runtime before interpreter exit.
  Callbacks capturing View/Runtime may form cycles across Python/native objects; explicit closing releases callback references.
- JSValue retains a value in the current document. Old handles raise `PageGone` after main-frame navigation or View closing
  and cannot be passed into other Views/documents. `JSValue.closed` reports explicit close, document invalidation, or View closing;
  operations still check document validity.
- Update/render callbacks may close Views, navigate, or replace callbacks, but cannot drive Renderer recursively.
  Navigation/closing during JS execution may make the current evaluation raise `PageGone`.

## Page events and exceptions

`view.set_callbacks(...)` replaces the whole callback set, clearing omitted callbacks. Supported callbacks:

| Callback | Argument |
| --- | --- |
| `begin_loading`, `window_ready`, `dom_ready`, `finish_loading` | Read-only `FrameEvent(frame_id, is_main_frame, url)` attributes |
| `fail_loading` | `LoadFailure`: `frame`, `description`, `domain`, `code` |
| `console` | Dictionary: `message`, `source`, `type`, `level`, `source_url`, `line`, `column` |
| `page_settled` | URL string after network/layout quiescence |

`view.on(event, callback)` adds an independent closable subscription. `set_callbacks()` does not affect those subscriptions or internal waits.

Event data has an independent lifetime and does not reference objects borrowed during SDK callbacks.
Events may include subframes; check `is_main_frame`. Loading completion does not guarantee success, so handle `fail_loading` separately.
Pages without scripts may not trigger `window_ready`; use `dom_ready` when depending on the DOM.

Synchronous engine errors raise `UltralightError`; script errors raise its subclass `JavaScriptError`.
Native diagnostics provide `code`, `stack`, `source_url`, `line`, and `column`.
Python argument-type errors use `TypeError`/`ValueError`; out-of-range integers use `OverflowError`.

Exceptions from Python functions, instance methods, and property access become JS Error in the page.
Page-event and resource-loader exceptions are isolated and passed to `runtime.set_error_handler(callback)`;
resource errors are dispatched during a later `update()` or shutdown.
The default reports through `sys.unraisablehook`; passing `None` restores it.
Exceptions from the error handler itself also use that hook and never propagate across the SDK boundary.

## Python and JavaScript

```python
def window_ready(event):
    if event.is_main_frame:
        view.bind_function("python_add", lambda a, b: a + b)


view.set_callbacks(window_ready=window_ready)
view.load_html("<script>window.answer=python_add(20,22)</script>")
# Advance update() and wait for the main-frame DOM before continuing:
assert view.evaluate("answer") == 42

with view.evaluate_handle("({offset:10, add(n){return this.offset+n}})") as obj:
    obj.set("offset", 20)
    with obj.get("add") as fn:
        with fn.call(2, this=obj) as result:
            assert result.to_python() == 22
```

`View.bind_function()` only binds the current document; it does not replay across navigation.
Rebind explicitly in each main-frame `window_ready`, or use the [standalone API registry](appcore.md#registration-and-restoration)
for attachment before loading and restoration after navigation.

`evaluate()` returns Python values; `evaluate_handle()` returns JSValue.
Handles support `get(str_or_int)`, `set(key, value)`, `keys()`, `call(*args, this=None)`, and `to_python()`.
`get()` and `call()` return handles; explicitly passing `this` preserves a method's receiver.
Individual `set()`/`call()` values and Python callable return values may be JSValue from the same document.
JSValue inside a live Python container is also checked for document ownership on access.
Explicit copying only accepts basic data/containers and does not copy special objects such as functions or Promises.

| Python | JavaScript |
| --- | --- |
| `None` | null |
| `ultralight_py.undefined` | undefined |
| bool | Boolean |
| int, float | Number; safe JS integers return int, others return float |
| str | String, preserving Unicode and embedded NUL |
| list | JS Array proxy; native JS Array becomes a shared JSArray view in Python |
| tuple | Read-only Python proxy, accessed through advanced Python indexing |
| dict | JS Object proxy with string-key properties; native JS objects become shared JSObject views in Python |
| Ordinary instance, callable | Attribute/method or callable proxy; restores the original object when returned |

Python int must fit within ±(2⁵³−1); no implicit string/number coercion occurs.
Mutable containers share references by default, including nesting, cycles, and aliases.
Special JS objects such as functions, Promise, and Date use JSValue.
For independent basic data, use evaluate(..., copy=True) or value.to_python(copy=True).
Explicit deep copying rejects cycles or depth beyond 64 and does not preserve aliases.
JSObject reads own enumerable string properties, potentially executing getters; keys() does not read values.

## Python objects and live containers

```python
class Counter:
    def __init__(self, value):
        self.value = value
        self.history = []

    def increment(self):
        self.value += 1
        self.history.append(self.value)
        return self.value


left, right = Counter(0), Counter(100)
left_binding = view.bind_object("left", left)
right_binding = view.bind_object("right", right)
view.evaluate("left.increment(); right.increment()")
assert (left.value, right.value) == (1, 101)
assert view.evaluate("left.history") is left.history
left_binding.close()
```

Public attributes, properties, and methods are exposed automatically; `members=[...]` narrows the root object's members.
Instances of the same class retain separate method/state handling. Each binding preserves object identity internally;
unbinding invalidates exported nested proxies and methods.
Document-level bindings must be recreated after main-frame navigation; the standalone API registry restores them automatically.
View retains PythonBinding sessions; dropping a handle does not unbind them.

Python list/dict and JS Array/plain objects share bidirectionally by default, including arguments, returns, and attributes.
JS uses indices, length, push, map, Object.keys, and JSON.stringify directly without making a snapshot first.
JS-created containers use JSArray/JSObject views in Python; explicit copy=True creates independent list/dict.
See [Object bridging](objects.md) for complete rules, dense arrays, non-string dict keys, and cleanup.

## Resource loading

```python
from ultralight_py import Resource, Runtime

files = {
    "page.html": Resource(b'<script src="app.js"></script>', "text/html"),
    "app.js": b"window.answer=42",
}
runtime = Runtime(assets_root="./assets", resource_loader=files.get)
view = runtime.create_view(320, 180)
view.load_url("file:///page.html")
```

Loading checks embedded ICU/certificates, the Python loader, then the local filesystem.
SDK resources are not passed to the Python loader. `assets_root=None` uses the working directory at first initialization;
explicit directories resolve to absolute paths.
The URL in `load_html(html, url="")` provides a base for relative resources; `load_url()` also supports HTTP/HTTPS.
Offscreen Runtime uses ulbind17's embedded fonts by default; Application uses AppCore system fonts.

`resource_loader(path)` returns `bytes`, `Resource(data, mime_type=None, charset="utf-8")`, or `None`.
Only `None` triggers filesystem fallback; exceptions or invalid return types fail that resource read.
Omitted MIME is inferred from the extension; encoding defaults to UTF-8.
SDK buffers own copies of the contents, including empty byte strings.

The SDK may repeatedly call the loader from the main thread or background loading threads.
Results are not cached; return consistent contents during one load and synchronize shared state yourself.
Do not operate on Runtime/View/JS inside the loader or wait for main-thread page progress.
Shutdown stops new loader calls, releases the GIL while waiting for active callbacks, then clears Python references.

## Pixels

`copy_pixels()` returns an immutable PixelBuffer owning independent bytes, usable after View closes.
Its fields are `width`, `height`, `row_bytes`, `format`, `dirty_bounds`, and `data`.
The format is always **BGRA8 with premultiplied alpha**; rows may contain padding.
Pixel `(x,y)` has byte offset `y * row_bytes + x * 4`.
`dirty_bounds` is `(left, top, right, bottom)`, with exclusive right/bottom edges.
Reading does not clear dirty bounds; call `clear_dirty_bounds()` after successful consumption.

`frame.to_rgba()` returns an immutable `RGBAImage` owning independent bytes: `width`, `height`, `data`,
and read-only `format == "RGBA8"`, `row_bytes == width * 4`.
Output is top-to-bottom, without row padding, and uses straight alpha; dimensions are unchanged.
`images.to_rgba(frame)` is the function entry point and also accepts an RGBAImage unchanged.
Images remain usable after View/Runtime closes. Conversion can run in a host thread pool;
the native pixel loop releases the GIL.

```python
from ultralight_py.images import to_numpy, to_pillow

rgba = frame.to_rgba()  # No Pillow/NumPy required.
image = to_pillow(rgba)  # pip install 'ultralight-py[pillow]'
image.save("capture.png")  # Pillow encodes PNG.
array = to_numpy(rgba)  # pip install 'ultralight-py[numpy]'
readonly = to_numpy(rgba, copy=False)
```

Pillow output is an independent mutable RGBA image.
NumPy output is a contiguous C-order `(height, width, 4)` uint8 array, writable and independent by default.
`copy=False` returns a read-only view of the RGBA bytes and keeps the underlying data alive.
It only avoids the array copy; BGRA unpremultiplication still allocates RGBA bytes.
Convert once and pass the same RGBAImage to multiple adapters to reuse the conversion.
Basic imports and RGBA conversion do not load Pillow/NumPy.

Unpremultiplication uses `min(255, channel * 255 // alpha)` and preserves alpha.
At alpha 0 all channels become zero; at 255 only channels are swapped.
The conversion preserves the engine's color space; information lost through 8-bit premultiplication cannot be recovered exactly.
It ignores row padding and extra trailing data. Input length must be at least `(height - 1) * row_bytes + width * 4`,
allowing an unpadded final row. Dimensions must be positive uint32; row stride must be a positive integer at least `width * 4`.
Input data must be bytes and format must be `BGRA8Premultiplied`.
Invalid types raise TypeError, invalid values/short buffers raise ValueError, size overflow raises OverflowError,
and allocation failure raises MemoryError. RGBAImage construction requires exactly `width * height * 4` bytes.

Scaling, background compositing, JPEG encoding, screenshot queues, and transport belong to the host application.
The [image example](../../examples/images.py) saves transparent PNGs; see `scripts/benchmark_images.py` for performance measurements.

## Input events

After the page is ready, send input to View on the main thread:

```python
from ultralight_py import KeyCode, Modifiers, MouseButton

view.focus()
view.click(40, 80, button=MouseButton.LEFT)
view.input_text("Hello, world 😀")
view.key_down(KeyCode.GK_BACK)
view.key_up(KeyCode.GK_BACK)
view.scroll(delta_y=-120, x=200, y=200)
```

`mouse_move()`, `mouse_down()`, and `mouse_up()` support dragging.
`click()` sends move, press, and release in sequence without implicitly focusing.
`focus()` and `unfocus()` control focus; `has_focus` and `has_input_focus` query View focus and editable-element focus respectively.
Coordinates use View logical pixels. Scrolling uses pixels by default, with positive values moving left/up and negative values right/down.
Pass `type=ScrollEventType.PAGE` for page scrolling. Default coordinates `(-1, -1)` use the current pointer position.

For full event fields, construct immutable `MouseEvent`, `ScrollEvent`, or `KeyEvent`
and pass them to `fire_mouse_event()`, `fire_scroll_event()`, or `fire_key_event()`.
Enum arguments require their corresponding enum type; integer arguments use signed 32-bit validation and reject bool/floats.
`KeyCode` retains SDK `GK_*` names. `Modifiers` combines ALT, CTRL, META, and SHIFT.
Mouse modifier state comes from the most recent keyboard event; hosts must forward modifier key presses and releases.

`key_down()` sends RAW_KEY_DOWN without inserting text; `key_up()` sends KEY_UP.
`input_text()` sends CHAR per Unicode code point and is intended for committed text.
It does not simulate physical keys or provide IME preedit/candidate positioning; AppCore handles IME in native windows.
Full KeyEvent supports native key codes, text, unmodified text, auto-repeat, keypad, and system-key flags.

Input follows main-thread, closed-object, and Runtime-busy checks.
Sending additional input inside Renderer, resource-loader, JS-bridge, or input callbacks fails;
queue it for the host's next iteration. Input callbacks may close View or Runtime.
Continue `update()`, `refresh_display()`, and `render()` after input, especially for scroll animations.

## Tkinter adapter and interactive example

Tkinter adaptation lives entirely in an optional Python module; native bindings only provide generic input events.
Ordinary `import ultralight_py` does not load tkinter or require Pillow.

```python
from ultralight_py.integrations.tkinter import TkInputAdapter

adapter = TkInputAdapter(canvas, view)
# The host drives Runtime using root.after() and turns copy_pixels() into Tk images.
# On window close, detach input before releasing View and Runtime:
adapter.close()
view.close()
runtime.close()
```

The adapter forwards pointer, buttons, wheel, focus, and keyboard events automatically.
An independent bindtag preserves existing host bindings. Focus loss releases keys/buttons;
widget destruction removes bindings automatically. `close()` is idempotent and only releases its callbacks,
scheduled work, and View reference, without closing View, Runtime, or the widget.
For scaled/offset page display, pass `coordinate_transform=lambda x, y: (x, y)` to map widget coordinates into View coordinates.

`wheel_pixels=40` sets pixel distance per standard wheel unit.
The adapter normalizes Aqua, Win32, and X11 wheel differences, maps Shift+wheel to horizontal scrolling,
and handles X11 auto-repeat release events. Printable characters and physical keys are sent separately;
shortcuts do not insert duplicate text.
macOS Aqua has been validated with a real window. Win32/X11 mappings have simulated-event coverage but await real-platform interaction validation.

```sh
python examples/tkinter_view.py
python examples/tkinter_view.py --smoke
```

The example includes buttons controlled by two separate Python Counter models, a text field, scrollable area, and event log.
It uses the standard library to convert opaque BGRA frames into PPM for Tk Canvas display.
The example host manages rendering, resize updates, and shutdown order.
`--smoke` creates a real window, checks frame dimensions/colors, Canvas images, and Python model isolation, then exits automatically.
It requires a graphical environment.
