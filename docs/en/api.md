# Public API

The public entry point is `ultralight_py`. `_native`, underscore-prefixed members, and internal wrapper constructors are not public interfaces.
Create a View through Runtime, obtain JSValue through View or JSValue, and obtain PythonBinding through binding methods.
Runtime manages the native Renderer. The project is under development and public interfaces may change.

For Application, Window, and the standalone API registry, see [Windows and the API registry](appcore.md).

## Runtime

| Interface | Returns and contract |
| --- | --- |
| `Runtime(*, assets_root=None, resource_loader=None, cache_path=None)` | Shared Runtime per process; directories accept str/PathLike; loader returns bytes, Resource, or None |
| `create_view(width, height, *, transparent=False, session=None)` | CPU offscreen View; dimensions must be positive uint32 values, excluding bool |
| `update()` | Advances page loading, scripts, and cleanup; does not render implicitly |
| `refresh_display(display_id=0)` | Notifies the engine of a display refresh for animations |
| `render()` | Renders offscreen pages that need updating |
| `set_error_handler(callback)` | Receives UltralightError; None restores the default unraisablehook |
| `close()`, `closed` | Idempotently closes all Views; the Renderer cannot be recreated afterward |

Exiting `with Runtime()` closes the shared instance. Do not use a temporary Runtime context around a host that is still in use.
The first configuration is frozen. Later calls that omit arguments reuse it; explicitly different directories or loaders raise ValueError.

`cache_path` specifies the root directory for Ultralight's disk cache and persistent browser storage, for example `Runtime(cache_path="./cache")`.
An explicit path is resolved to an absolute path during first initialization, independently of `assets_root`.
It accepts str/PathLike and rejects paths containing NUL.
`None` keeps the SDK defaults; later calls with `None` reuse the initial configuration without resetting the directory.
The same directory can be specified repeatedly; a different directory raises ValueError. The SDK creates directories as needed.
Views on the same Runtime share the default browser Session and its storage. This setting does not isolate accounts;
use [Session](#session) for storage isolation.

## View

| Interface | Returns and contract |
| --- | --- |
| `load_html(html, url="")`, `load_url(url)` | Starts asynchronous loading; the HTML URL is the base for relative resources |
| `resize(width, height)` | Changes device pixel dimensions; same validation as create_view |
| `set_callbacks(*, begin_loading=None, window_ready=None, dom_ready=None, finish_loading=None, fail_loading=None, console=None, page_settled=None)` | Replaces the whole set of legacy callback slots; leaves subscriptions and internal waits intact |
| `on(event, callback)` | Returns Subscription; supports the seven events above |
| `is_ready`, `is_settled` | Current main-page state; reset when loading starts or fails |
| `navigation_id`, `load_failure` | Navigation generation and the current main-frame LoadFailure or None |
| `wait_ready(timeout=5)`, `wait_settled(timeout=5)` | Passive asynchronous waits; return None on success |
| `wait_until(predicate, timeout=5)` | Passively waits for a synchronous predicate; returns its first truthy result |
| `wait_for_selector(selector, timeout=5)` | Waits for an element to exist in the main document; returns True; does not check visibility |
| `evaluate(source, *, copy=False)` | Evaluates JS; containers are shared by default, copy=True recursively copies; does not wait for page loading |
| `evaluate_handle(source)` | Retains a JSValue in the current document |
| `bind_object(name, instance, *, members=None)` | Returns PythonBinding; name must be a nonempty string other than the reserved name Python |
| `bind_function(name, callback)` | Callable-specific entry point; returns PythonBinding and preserves the original object's identity |
| `unbind(name)` | Revokes the named binding; a missing name is a no-op |
| `copy_pixels()` | PixelBuffer with independent bytes; reading does not clear dirty bounds |
| `clear_dirty_bounds()` | Clears dirty bounds after the host successfully consumes the frame |
| `close()`, `closed` | Idempotent close; exiting a context also closes the View |

For members, container operations, and conversion rules, see [Object bridging](objects.md).
See [Input events](guide.md#input-events) for input methods; inherited input APIs are also part of the public View interface.
Use `window_ready` to install bindings before page scripts execute and `dom_ready` to wait for the DOM.
FrameEvent and LoadFailure are independent, read-only event data; console receives an ordinary dictionary.
Events may originate from subframes; main-page logic should check `is_main_frame`.

## Page waits and event subscriptions

View waits never call `update()`, `refresh_display()`, or `render()`, and never install a driver.
The host retains full control of its frame loop. Lifecycle waits observe events; condition waits check once initially,
then only recheck after the host's `Runtime.update()` or AppCore step. They do not poll continuously without engine steps.

Call `load_html/load_url` first, then wait for the page being loaded. `wait_ready` only means the main-frame DOM has been parsed.
`wait_settled` means the SDK's network and layout quiescence detection has completed; it requires the host to keep performing
updates, display refreshes, and renders. Application handles that loop. It does not guarantee business logic is complete or animations have stopped permanently.
Before a new View has loaded anything, `is_ready` is False and waits remain subject to their timeout.

`navigation_id` advances immediately for Python-initiated loads; the corresponding main-frame loading event does not increment it twice.
New main-frame loads initiated by the page also advance the generation; subframes and `window_ready` do not.
Ordinary waits belong to the document current when they start; replacement raises `UltralightError(code=PageGone)`.
Loading failure raises `PageLoadError`, whose `failure` holds the original LoadFailure; closing raises `Closed`.
Validity is checked again if navigation or closing occurs after the ready event but before the wait resumes.

`timeout` must be a finite positive number of seconds, excluding bool and None. Expiration raises `TimeoutError`;
cancellation propagates `asyncio.CancelledError`. Canceling a wait does not stop loading or JS work.
`wait_until` rejects asynchronous predicates and propagates predicate exceptions directly; invalid selector syntax raises JavaScriptError.

```python
# The host frame loop advances runtime; these waits do not.
view.load_url("file:///panel.html")
await view.wait_ready(timeout=5)
await view.wait_for_selector("#status")

with view.on("dom_ready", callback) as subscription:
    ...
```

View retains subscriptions. Dropping a subscription handle does not cancel it; call `close()` or exit its context.
Closing View/Runtime releases subscriptions and legacy callbacks. Internal state updates first, followed by the legacy callback
and independent subscriptions in registration order. A callback exception goes to the Runtime error handler; the remaining subscribers still run.
Subscriptions added during dispatch start receiving the next event; closed subscriptions stop immediately.
All event callbacks must be synchronous; `page_settled` receives a URL string.

## Optional script driver

`ultralight_py.scripting.ScriptDriver` borrows a Runtime; `driver.page(view)` returns a ScriptPage borrowing the View.
Create only one ScriptDriver per Runtime and share it across pages. Construct and use it in the same asyncio loop on the main thread.

```python
from ultralight_py.scripting import ScriptDriver

# Standalone scripts can explicitly select the library's on-demand loop.
async with ScriptDriver.auto(runtime, update_interval=1 / 60, display_id=0) as driver:
    page = driver.page(view)
    await page.navigate("file:///panel.html", wait_until="settled", timeout=5)
    result = await page.evaluate("getResult()")
    frame = view.copy_pixels()

# With an existing host scheduler, step requests progress; the host decides when.
async with ScriptDriver(runtime, step=host.request_step) as driver:
    await driver.page(view).wait_ready()
```

The host callback contract is `async def request_step(*, render: bool = False) -> None`.
Returning means one `update()` and `refresh_display()` have completed, plus `render()` if `render=True`.
Requests can be queued, rate-limited, and merged into the host's next frame. The adapter does not call the engine directly.
Multiple waits share one in-flight request; render demand arriving too late for that request is included in the next step.

ScriptPage offers View's four waits, plus `evaluate(source, timeout=30)`,
`navigate(url, *, wait_until="ready", timeout=30)`, and `load_html(html, url="", *, wait_until="ready", timeout=30)`.
All default timeouts are 30 seconds. Ordinary document or condition waits request updates and display refreshes;
page-settled and JS Promise waits request complete frames. In Beta.2, a requestAnimationFrame Promise needs rendering to complete,
so asynchronous evaluation also requests rendering. Immediately satisfied conditions and immediate JS values request no steps.
Pass `render=True` for conditions/selectors depending on rAF or layout. Use `page.evaluate(..., render=False)`
when evaluation only needs script timers. These parameters express demand; the host still decides when to perform a complete frame.

For navigation caused by clicks or form submissions, register the observer before the action using a context:

```python
async with page.expect_navigation(wait_until="ready", timeout=30):
    page.view.evaluate("setTimeout(() => document.querySelector('a.next').click(), 0)")
await page.wait_for_selector("#result")
```

On context exit, it waits for the new main page; an already-ready old page does not complete it early.
No navigation results in a timeout. The action and wait share a monotonic-clock budget.
Action errors or cancellation immediately release observers; asynchronous actions are also timed out.
Timeouts cannot preempt synchronous Python/JS. Synchronous JS navigation may make evaluation itself raise PageGone;
the example uses a zero-delay task so evaluation returns first. The context does not swallow action exceptions.
`navigate` and `load_html` use the same context internally.

Navigation operations register their request before acting and allow engine navigation chains to continue while the operation is pending.
A new Python load after navigation starts interrupts the old operation with PageGone.
The SDK exposes no navigation cause/request ID, so page-initiated redirects before completion also join the current chain;
redirects after completion are not tracked. The entire chain shares one timeout budget, regardless of redirect count.

Automatic mode advances at the configured interval while waits demand progress, and stops when idle.
It is mutually exclusive with `integrations.asyncio.install()`.
Closing ScriptDriver ends its own operations and step requests; it does not close the borrowed View/Runtime or terminate other passive waits.
A custom host can operate entirely through state and synchronous subscriptions without a driver.

## JSValue and PythonBinding

| Interface | Returns and contract |
| --- | --- |
| `JSValue.get(key)` | Property-value handle; key must be str/int, excluding bool |
| `JSValue.set(key, value)` | Sets a property; accepts basic values, live Python proxies, and JSValue from the same document |
| `JSValue.keys()` | List of own enumerable string property names, without reading values |
| `JSValue.call(*args, this=None)` | Result handle; a same-document JSValue for this preserves the JS method receiver |
| `JSValue.to_python(*, copy=False)` | Shares containers by default; copy=True recursively copies to independent basic Python data |
| `JSValue.close()`, `closed` | closed covers explicit close, document invalidation, or a closed View |
| `PythonBinding.close()`, `closed` | Revokes all proxies exported by the binding; navigation/closing also makes closed true |

Both handle types support `with`. Dropping PythonBinding does not unbind; dropping JSValue releases its retained handle,
possibly deferred until a main-thread call. There is no general `valid` property; operations check document validity.
A Python callable exported through `bind_function/bind_object` is restored to the original object when passed back.
Separate explicit bindings retain independent proxy identities and revocation scopes.

JSArray (MutableSequence) and JSObject (MutableMapping) are created automatically by evaluation, callbacks, and property access.
They support close/closed, with, and to_python(copy=True). JSObject only operates on own enumerable string properties.
View.evaluate_async and ScriptPage.evaluate also accept the keyword argument copy=False.
For shared views, mixed keys, and migration rules, see [Object bridging](objects.md).

## Image output

`PixelBuffer.to_rgba()` and `ultralight_py.images.to_rgba(frame)` return `RGBAImage`.
Import RGBAImage from the root package or images module; construct it with `RGBAImage(width, height, data: bytes)`.
Its immutable attributes are width, height, data, row_bytes (width * 4), and format (`"RGBA8"`).
Pixels use straight-alpha RGBA in contiguous rows without padding. It is independent of Runtime/View and conversion does not create a Renderer.
The function accepts PixelBuffer or RGBAImage and returns an RGBAImage input unchanged.

| `ultralight_py.images` interface | Output |
| --- | --- |
| `to_pillow(frame)` | Independent, mutable Pillow RGBA image; requires the `[pillow]` extra |
| `to_numpy(frame, *, copy=True)` | Independent writable contiguous C-order uint8 array of shape `(height, width, 4)`; requires `[numpy]` |
| `to_numpy(frame, copy=False)` | Read-only view of the converted RGBA bytes, keeping the underlying data alive |

Adapters accept PixelBuffer or RGBAImage and load dependencies when called. Missing dependencies raise ImportError with installation instructions.
For strides, unpremultiplication, validation, and ownership, see [Pixels](guide.md#pixels).

## Data and errors

`Resource(data: bytes, mime_type=None, charset="utf-8")` copies resource data.
Omitting mime_type stores an empty string, not Python None; loading infers MIME from the file extension.
`PixelBuffer` is an immutable data class with width, height, row_bytes, format, dirty_bounds, and data.
The format string is `BGRA8Premultiplied`; see [Pixels](guide.md#pixels) for layout and row offsets.
`undefined` is a singleton; use `value is undefined` to distinguish JS undefined from None/null.

UltralightError inherits RuntimeError; JavaScriptError inherits UltralightError.
Diagnostic fields are code, stack, source_url, line, and column. Missing positions use native diagnostic defaults.
ErrorCode is a native enum supporting `.name`, `.value`, and `int(code)`; Python Enum iteration is not guaranteed.
Common errors:

| code | Common cause |
| --- | --- |
| WrongThread | Engine operation or explicit handle close outside Python's main thread |
| Closed | Runtime, View, Window, Application, or API is closed |
| PageGone | The JS handle's document was invalidated, or a Python binding was revoked |
| CrossContext | JSValue belongs to another document, or Session/View belongs to another Runtime |
| Busy | Renderer/input reentry, or engine operations inside a resource callback |
| ScriptException | JS execution failure, represented by JavaScriptError |
| TraversalLimit | Explicit copying encountered a cycle or exceeded the depth limit |
| Unsupported | Manually driving an AppCore Runtime, or reading CPU pixels from an accelerated View |

Python argument validation may also raise TypeError, ValueError, or OverflowError directly.
Python bridge exceptions become JS Error in the page; page code can catch them and continue.
Event and resource exceptions go through the Runtime error handler; see [Page events and exceptions](guide.md#page-events-and-exceptions).

## Threads and optional integrations

Engine operations and explicit close run on Python's main thread; the host drives the loop.
closed is a state query and does not start engine operations; PythonBinding.closed may be queried from other threads.
Resource loaders may run on background threads and must not operate on Runtime/View/JS or wait for main-thread loading progress.
Additional input from input callbacks, Renderer callbacks, or JS bridging should be queued for the host's next iteration.

`ultralight_py.integrations.tkinter.TkInputAdapter(widget, view, *, coordinate_transform=None, wheel_pixels=40)`
only adapts input. close removes its own bindings and borrowed references without closing View, Runtime, or the widget.
Rendering, frame conversion, and scheduling are the host's responsibility. Ordinary imports do not require tkinter or Pillow.
Event callbacks are synchronous; Promise/asyncio bridging is covered next.

## Promise and asyncio

`await JSValue.await_result()` waits for a JS Promise and returns a `JSValue` that must be closed.
A non-Promise raises `TypeError`; rejection raises `JavaScriptError` with the error message.
`await View.evaluate_async(source)` evaluates and returns a Python value, converting ordinary results directly.
`await JSValue.call_async(*args, this=None)` returns a `JSValue`, including for ordinary results.
Navigation or closing ends waits with `UltralightError(code=ErrorCode.PageGone)`.
Canceling a Python wait removes the bridge listener; the JS Promise itself continues.

When a bound function or object method returns an awaitable, JS receives a Promise.
asyncio schedules the Python task; results reach JS during a later Runtime update or AppCore step, and exceptions reject the Promise.
Unbinding, replacing bindings, navigation, and closing immediately revoke delivery and request cancellation of bridge-created Tasks.
Externally supplied Task/Future objects are only detached, never canceled by the bridge. Cancellation is cooperative.

```python
from ultralight_py.integrations.asyncio import run, install

run(main(), runtime=runtime, update_interval=1 / 60)

# With an already-running asyncio loop:
driver = install(runtime, update_interval=1 / 60)
try:
    result = await view.evaluate_async("Promise.resolve(42)")
finally:
    driver.close()
```

`await` does not implicitly advance the engine. A custom offscreen host can call `update()` itself without installing a driver.
The first asynchronous operation associates the current loop; a Runtime allows only one loop and one driver at a time.
Engine operations must run on the main thread. The offscreen driver above only updates; it does not render or close the supplied Runtime.
AppCore applications use `run/run_async`; see [Loops and shutdown](appcore.md#loops-and-shutdown).
The update interval is a target scheduling interval; blocking the host thread or running long JS delays updates.
Driver close/failure ends associated cross-language waits and deliveries. `run()` propagates driver errors and cleans up timers,
listeners, and tasks on exit. JS Promises may remain pending after driver shutdown.
A combined Tk/asyncio loop and JS AbortSignal are currently unavailable.

## Session

`Runtime.create_session(name, *, persistent=False)` creates a browser storage session; Views in the same Session share storage.
`get_session(name)` returns an open session or `None` without scanning disk.
`get_or_create_session(name, *, persistent=False)` reuses an open session; mismatched persistence raises `ValueError`.
Creating a duplicate name also raises `ValueError`.

Names must match `[a-z0-9_-]{1,80}`; `default` and Windows device names are reserved.
Invalid names raise `ValueError`; incorrect argument types raise `TypeError`.
`persistent` and `force_close` accept only bool.

Specify `session=session` when creating a View. `View.session` is read-only and cannot be changed afterward.
Omitting it uses the SDK default session and the property returns `None`.
Creating a View with a closed session raises `Closed`; a session from another Runtime raises `CrossContext`.

Session has read-only name, persistent, disk_path, and closed attributes.
Temporary sessions have `disk_path=None`; persistent sessions use named subdirectories under the cache root and return
the absolute `Path` reported by the SDK. Cookies with expiration dates, localStorage, and IndexedDB survive normal shutdown;
the SDK provides no explicit storage-flush interface. Different sessions isolate storage; `sessionStorage` remains per View.

Runtime keeps open Sessions alive; Views keep their Session alive. A Session remains reusable after all its Views close.
`session.close()` raises `Busy` while associated Views live. `close(force_close=True)` closes those Views and cleans up their waits,
subscriptions, JS handles, and async bridges; Views in other sessions continue operating.
Closing is idempotent, leaves metadata readable, and does not delete persistent data.
Recreating a temporary session with the same name starts empty; a persistent session reuses its storage directory.

Context exit calls ordinary `close()`, so close associated Views first.
Runtime closes Views, explicit Sessions, and then the Renderer. Session operations follow main-thread and resource-callback restrictions;
`force_close` only bypasses the associated-View occupancy check. Sessions isolate browser storage only.

See the [multi-session example](../../examples/sessions.py).
