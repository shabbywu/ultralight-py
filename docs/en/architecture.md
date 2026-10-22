# Architecture and maintenance

The project has three layers: ulbind17 supplies cross-language hosting, native bindings manage the Python/JSC boundary,
and Python provides the public API, Python semantics, and optional host integrations.
It supports CPU offscreen rendering, AppCore native windows, and synchronous/asynchronous bidirectional bridging.

| Layer | Responsibility and boundary |
| --- | --- |
| `externals/ulbind17` | Renderer/ManagedView, document invalidation, generic Bridge/Handle, input and resource infrastructure |
| `bindings/` | Python conversion, GIL, exception translation, deferred reference release, Python object proxy sessions |
| `src/ultralight_py/` | Public wrappers/validation, member policy, Python operations, input convenience methods |
| `src/ultralight_py/integrations/` | Optional window-framework adapters, kept out of generic C++ bindings |

## Python dependencies

`__init__.py` and its type stub only aggregate public exports.
`api/` separates Runtime/Session/View/JSValue/PixelBuffer into runtime, view, and values;
`input.py` supplies data and the input mixin; `objects.py` supplies PythonBinding.
`appcore/` separates Application/Window into application and window, while `registry.py` supplies the standalone API registry.
Shared internals are imported through private modules: `_objects.py` provides native-proxy member policy and operations;
`_asyncio.py` manages loop association, Promise waits, and deferred delivery; `_validation.py` validates input;
`_support.py` supplies main-thread checks and native-call wrappers.
`_lifecycle.py` registers process-exit cleanup once, when Runtime or Application is first created.
The root entry point exports errors, resources, and page events from `_native` and `_waiting`.
`integrations/asyncio.py` retains the public Driver, install, and run interfaces.
`_waiting.py` manages page generations, event dispatch, and passive waits; `events.py` provides Subscription.
`scripting.py` coalesces script step demand, borrowing a host callback by default; `auto()` explicitly manages an on-demand loop.
Condition predicates recheck only after Runtime updates or AppCore steps return from native calls.
View's fixed internal dispatcher uses weak references for native callbacks; replacing legacy callback slots does not remove internal observers.
Runtime notifies Python Views of closing/updates through weak sets.
Helpers inside private modules do not use underscore prefixes; callers import modules and use forms such as `_support.call(...)`
and `_asyncio.await_result(...)`.
Imports belong at module top level and use absolute paths. Mutually dependent modules import module objects first,
then access type attributes when functions run, avoiding reads of undefined types during initialization.
Native calls share `_support.py`'s main-thread entry and cleanup. Input and binding close do not depend back on public api modules.
`_objects.unwrap()` recognizes public handles/container views through `_api.JSValue/JSArray/JSObject`, without reading undefined types at initialization.

`api/__init__.pyi`, `input.pyi`, `objects.pyi`, `events.pyi`, and `scripting.pyi` describe their respective modules.
The root stub defines native public types and re-exports Python API types, avoiding distinct static types at root/module entry points.
The Tk adapter has its own stub. Public callables go directly into object binding instead of temporary Python wrappers that change identity.

## Native modules

Keep implementations header-only; `module.cpp` only establishes registration order.
Organize modules by responsibility without splitting into multiple cpp files.
Runtime/View use forward declarations for mutual references; ownership operations requiring complete types live in `runtime/views.hpp`.
View/JSValue cross-operations live in `view/javascript.hpp`; pixel output lives in `view/pixels.hpp`.
AppCore application, window, and registration entry points live in `appcore/application.hpp`, `window.hpp`, and `bindings.hpp`.
Image conversion lives in `images/conversion.hpp`, with registration in `images/bindings.hpp`.

Object bridging headers:

| Header | Responsibility |
| --- | --- |
| `state.hpp` | Ownership, lookup, and revocation for Document, Session, and Node |
| `factory.hpp` | JS Proxy factories and the reserved Python namespace |
| `proxy.hpp` | Member callbacks, callable invocation, and identity conversion within sessions |
| `iteration.hpp` | Python iterator adaptation and reference release on completion/early exit |
| `operators.hpp` | JS Python operations, binding-scope selection, and exception translation |
| `document.hpp` | Document initialization, lifecycle guards, and generic conversion wiring |
| `async.hpp` | JS Promises for Python awaitables, session revocation, and SDK PostTask delivery |

`conversion.hpp` separates default shared conversion, explicit deep copying, and internal argument-list unpacking.
Only explicit deep copying uses ulbind17 Traversal cycle/depth limits.
Python list/dict use dedicated Array/Object Proxies; JSArray/JSObject in api.values implement Python container protocols using independent HostValue handles.
Document weakly references HostView and owns a Python WeakValueDictionary; a JS WeakMap assigns object identities,
avoiding strong ownership of Python views through identity caches.
Returned proxies restore original objects. JS array detection uses a captured Array.isArray because the SDK's JSC C API does not recognize array Proxies.
Public Python `bind_function()` checks callability; native binding uniformly uses bind_object.

Container reads use private numeric opcodes, passing list indices to native code as numbers.
Ordinary built-in scalars return directly from native callbacks; conversion and explicit copying share integer-range and UTF-16 handling.
Scalar subclasses may reenter JS during destruction, so they retain the handle-based conversion path.
Existing proxies for exact built-in list/dict are retained by Session Nodes. After validity checks,
callbacks can borrow proxies directly, avoiding temporary Handles and their PostTask release.
Values stored across calls must still be retained.

## Ownership and cleanup

Runtime strongly retains open native View wrappers; View weakly references Runtime.
Closing a View removes it from Runtime's list, with a local strong reference protecting the active close operation.
Runtime closing first detaches the list, then closes each View. Python View collection only queues cleanup,
avoiding SDK destruction on arbitrary threads.

Browser storage uses HostSession, distinct from object bridging's objects::Session.
Python Runtime strongly retains open public Sessions; Python View retains the Session specified at creation.
Native Runtime strongly retains open HostSessions, HostView strongly retains HostSession, and HostSession weakly references Runtime.
Ordinary Session close checks the native View list for occupancy; forced close only closes associated Views.
It removes the session from the registry after releasing the SDK Session reference.
Python synchronously clears closed-View waits/subscriptions; native View closing invalidates JS handles and async bridging.
Runtime closes Views, explicit Sessions, then Renderer. The SDK manages persistent directories; closing does not delete disk data.

Every valid document retains Document through a Bridge lifecycle guard.
Document strongly owns implicit/named Sessions; Session owns Nodes and iterator references; reverse links are weak.
JS proxy payloads do not strongly retain Python objects. Document invalidation clears guards, revokes sessions, then releases objects.
The document registry holds weak references only; destruction removes its record so long-running navigation does not accumulate stale entries.
Registry access and guard revocation occur on the document's thread; other threads may only query atomic binding-closed state.

Native Python strong references are wrapped by PythonRef.
Destruction only queues PyObject; draining occurs on the main thread while holding the GIL.
JSC garbage collection/finalizers do not acquire the GIL.
Sessions retain proxies by identity until revocation/document invalidation, rather than using JS GC to infer Python reachability.
Unconsumed or early-returned iterators also remain until session invalidation.
Python callbacks capturing View/Runtime may form cross-language cycles; applications should close explicitly.

Dynamic registration entry points, JS factory callbacks, and interpreter-exit hooks must not be removed as unused merely because they lack static call edges.
Embedded fonts, the SDK resource overlay, and pinned downloads continue to reuse ulbind17 instead of introducing another generic runtime.

## Async bridging

`_asyncio.py` manages loop association, task listeners, and deferred delivery.
Native `async.hpp` scopes delivery by document/binding sessions and writes back through SDK PostTask.
Cancellation, unbinding, navigation, closing, and driver failure revoke relevant work; asyncio/Tk state remains in Python's host layer.

Page state lives in PageState. Raw events still dispatch, while hosts read View state for the current document,
preventing stale events after reentrant navigation from incorrectly restoring cached readiness.
Wait handles register synchronously before awaiting results.
ScriptPage.expect_navigation registers before the action, sharing a deadline across action/page waiting.
Passive waits bind to the current document; navigation contexts bind to observed load requests.
Engine redirect chains may continue, while a later explicit load invalidates them.
Both request host progress through the same ScriptDriver.

## AppCore and persistent registries

`appcore/` separates Application/Window and continuous asyncio driving into application/window; `registry.py` provides standalone API.
Native `bindings/appcore/` connects the existing HostRuntime through ulbind17 Application, using ManagedView/AdoptPanel for windows.
AppCore platform initialization preserves Python FileSystemOverlay and uses system fonts.
Window Views use window defaults; offscreen Views remain CPU-based. AppCore exclusively drives Renderer.

The standalone registry's `registry/api.hpp` owns Python definitions; `attachments.hpp` handles attachment, replay, and revocation;
`bindings.hpp` registers Python interfaces.
View's internal `window_ready` callback uses the existing dynamic Bridge to create namespaces and document sessions.
It complements the SDK's typed js::API rather than replacing dynamic Python objects with C++ class registration.
Entries are isolated by View/document; navigation only rebuilds document sessions.
View strongly retains attached registries; registries weakly reference View.
Documents retain sessions only; old-session invalidation immediately revokes proxies/delivery.
Closing the last View does not clear definitions; API.close releases all registered references.

HostView's independent close notification synchronizes Python PageState for explicit View close, forced Session close,
and AppCore native-window close. Window closing clears documents/waits before dispatching user close events;
the last window closes Application and Runtime.
run_async completion, cancellation, and failure use the same shutdown path and allow asyncio cancellation callbacks to run.
ScriptDriver(app.runtime) only waits for application frame notifications; window driving never stops because script demand is idle.
