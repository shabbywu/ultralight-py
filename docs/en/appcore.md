# Native windows and the Python API registry

`Application` uses AppCore for system fonts, window layout, DPI, system input, and IME.
Window pages use the existing `View`; resource loading, Session, object proxies, and Promise bridging share the same implementation.

## Quick start

```python
import asyncio
from ultralight_py import API, Application

with API("app") as api, Application() as app:

    @api.register
    async def hello(name):
        await asyncio.sleep(0)
        return f"Hello, {name}"

    window = app.create_window(800, 520, title="Python native window")
    api.attach(window.view)
    window.view.load_html("""
        <input placeholder="Enter text">
        <script>
        app.hello('world').then(value => document.body.append(value));
        </script>
    """)
    app.run()
```

Create `Application` before the first Runtime. `app.runtime` is the existing Runtime type;
subsequent `Runtime()` calls return the same instance. The engine cannot be recreated after shutdown.
Application accepts `assets_root`, `resource_loader`, and `cache_path` with the same meanings as Runtime.
`app_name` and `developer_name` default to `ultralight-py` and determine AppCore's default storage directory.

The complete example uses Python virtual resources, Session, decorators, and asynchronous functions:

```sh
python examples/appcore.py
python examples/appcore.py --smoke
python examples/appcore.py --cpu --smoke
```

## Windows and Views

`app.create_window(width, height, *, title="", session=None, view=None,
transparent=False, resizable=True, fullscreen=False)` creates a window.
Dimensions must be finite positive numbers in logical pixels. By default, it creates a View filling the window.
An explicit Session must belong to `app.runtime`. To use an existing View, pass `view=...`;
it must be unhosted and belong to the application Runtime, and Session cannot also be specified.
An existing View retains its rendering and font configuration; Panel handles later layout and DPI changes.

Window exposes `view`, `closed`, `width/height`, `device_width/device_height`, `device_scale`, and a writable `title`.
`on("resized", callback)` receives a logical-size tuple; `on("closed", callback)` receives None.
Both return the existing Subscription type. Callbacks run synchronously; exceptions go to the Runtime error handler.
The window's View and associated waits are already closed before the close notification runs.

New window Views follow AppCore's rendering configuration; `force_cpu_renderer=True` selects CPU rendering.
An accelerated View's `copy_pixels()` raises `Unsupported`; `app.runtime.create_view()` still creates CPU offscreen Views.
Window owns the hosted View and Python wrapper; dropping external View references does not close the page.
AppCore automatically forwards system input, with focus managed through Panel; IME uses AppCore's editing listener.

## Registration and restoration

`API(namespace)` uses an ASCII JavaScript identifier as its global namespace; `Python`, `ul`, and `ultralight` are reserved.
Registered entry names must also be ASCII JavaScript identifiers.

| Interface | Behavior |
| --- | --- |
| `register(function, *, name=None)` | Registers by function name or explicit name; returns the original function |
| `@api.register`, `@api.register(name="save")` | Decorator forms; support synchronous and asynchronous callables |
| `register_object(name, instance, *, members=None)` | Uses the existing Python object proxy and member restrictions |
| `unregister(name)` | Removes the definition and revokes old proxies in every attached View's current document; a missing name is a no-op |
| `attach(view)` | Attaches before loading, or installs immediately in the current document; repeated attachment of the same API is a no-op |
| `detach(view)` | Immediately revokes that View's proxies and stops restoration after navigation |
| `close()`, `closed` | Revokes all attachments and releases definitions; closing is idempotent |

Define a registry before creating Runtime if needed, and attach it to multiple Views.
Two registries cannot use the same namespace in one View; attaching fails if the page already has a conflicting global.
Adding or replacing a definition immediately updates all attached Views and revokes old bindings, nested proxies, methods, and async deliveries.

The internal main-frame `window_ready` installs the registry before the first page script, then notifies user callbacks.
Main-frame navigation revokes the old document's sessions and restores the latest definitions in the new document.
Replacing user page callbacks does not remove this replay. Injection targets only the main frame and continues across future navigation;
call `detach()` explicitly to stop exposing the API.
Each entry has an independent proxy session per document; see [Object bridging](objects.md) for object, container, and asyncio semantics.
`View.bind_object/bind_function` remain available for temporary exports in the current document.

Closing a View or detaching the last View does not clear registered definitions.
API retains objects until unregistration, replacement, or close; use `with API(...)` to release references promptly.
View retains its attached native registry; the registry holds a weak reference to View.

## Loops and shutdown

`app.run()` creates an asyncio loop on the main thread and continuously drives windows.
With an existing loop, use `await app.run_async(update_interval=1/60)`. The interval must be finite and positive.
Each AppCore iteration processes system events, updates, display refreshes, and rendering, along with async delivery, condition checks, and cleanup.
It keeps running even without page waits, so page animations and system input remain active.

`run_once()` lets an external host step manually and returns whether the application is still alive; the host advances asyncio itself.
Additional stepping during automatic running is forbidden, and neither step nor run entry points permit reentry.
AppCore Runtime's `update/refresh_display/render`, offscreen asyncio `install()`, and `ScriptDriver.auto()` raise `Unsupported`.
For the script interface, use `ScriptDriver(app.runtime)` inside the application loop;
it waits for application frame notifications instead of starting another engine loop.

Closing a window revokes its document proxies, JS Promise listeners, page waits, and bridge deliveries; other windows continue.
Closing the last window exits the application and closes explicit Sessions, resource loading, and Runtime.
Closing a View alone, or force-closing a Session, only removes the relevant Panel; the window remains alive.
Closing Runtime or Application closes all windows. Closing is idempotent; old JS handles raise `PageGone`.

Canceling `run_async()` or a driver failure also closes the application and propagates the original exception; the caller's asyncio loop stays running.
The bridge requests cancellation of Python Tasks it created, but only detaches external Task/Future objects.
Cancellation is cooperative and tasks must handle it normally. Document and deferred Python references are cleaned up on the main thread;
standalone API definitions still follow the explicit-close rules above.

## Platform validation

Release configuration includes AppCore libraries for Windows x64, Linux x64, and macOS ARM64.
Native macOS desktop tests cover default/CPU rendering, DPI and pixel dimensions, resource loading, multiple windows,
Sessions, async driving, and shutdown on macOS ARM64. Windows/Linux desktop interaction requires validation on those systems.

Use the interactive example to check Chinese system fonts, window movement/resizing, DPI across displays,
Chinese composition, candidate-window positioning, copy/paste, and focus changes.
Real multi-display DPI and input-method combinations require local interaction; automated tests do not simulate IME.
