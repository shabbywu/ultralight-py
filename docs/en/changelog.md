# Changelog

## 0.6.1 (unreleased)

- Optimize frequent JS reads of Python list/dict: built-in containers use native read paths with fewer repeated lifecycle checks and Python dispatches.
- Use numeric read opcodes and numeric array indices. Return ordinary built-in scalars directly and reuse existing nested-container proxies, reducing temporary handles and deferred release.
- Preserve live sharing, proxy identity, subclasses, awaitables, safe integer ranges, and Unicode semantics; add regressions for key comparison/destructor reentry and binding revocation.
- Add reproducible container-read benchmarks comparing live proxies, pre-copied data, and copying plus reads; document local measurements and snapshot choices for intensive computation.

## 0.6.0

- **Breaking:** mutable containers share bidirectionally by default. Python list/dict support indices, length, native Array methods, Object enumeration, and direct JSON serialization in JS; JS Array/plain objects become JSArray/JSObject views in Python.
- Add copy=True to evaluate, evaluate_async, ScriptPage.evaluate, and to_python for independent Python list/dict snapshots. Default sharing supports aliases, cycles, and mixed cross-language containers.
- Keep Python lists dense, filling holes with undefined. Dict JS properties expose string keys only; non-string keys use advanced Python operations.
- Stop exposing Python methods as list/dict JS properties; use Python.getattr. JSON.stringify no longer requires Python.to_value. See [Object bridging](objects.md#explicit-copying-and-060-migration) for migration.
- Container views retain independent handles; identity caches use weak references, preserving binding isolation, document invalidation, and thread checks.

## 0.5.0

- Exclude OS-loaded `ext-ms-win-*` API sets when repairing Windows wheels so missing AppCore DLL dependencies do not fail analysis.
- Split API and AppCore into public submodules supporting imports from `api.runtime`, `api.view`, `api.values`, `appcore.application`, and `appcore.window`.
- Export errors, resources, and page events consistently from the root `ultralight_py` entry point; register process-exit cleanup on first Runtime/Application creation.
- Add AppCore Application/Window with system fonts, DPI, native input, and IME, reusing Runtime, View, resources, and Session.
- Add standalone API registries, `@api.register`, object proxies, pre-load attachment, navigation restoration, and immediate definition updates/revocation.
- Add synchronous/asyncio application loops and manual stepping. Unify window closing, page waits, async delivery, and Python reference cleanup; bundle AppCore in wheels.
- Add native Session creation, lookup, reuse, persistence, and close. Views can specify Sessions; closing checks associated Views and supports forced closure.
- Add independent RGBAImage, native BGRA/stride/unpremultiplication conversion, and lazy optional Pillow/NumPy adapters. Conversion can run in a thread pool.
- Add multiple event subscriptions and main-frame page state; replacing legacy callback slots leaves internal waits/subscriptions intact.
- Add passive `wait_ready/wait_settled/wait_until/wait_for_selector` and structured PageLoadError, handling navigation, closing, timeouts, and cancellation.
- Add optional ScriptDriver with injected host stepping or explicit shared on-demand driving; script navigation follows pending engine navigation chains.
- Add `ScriptPage.expect_navigation`, registering before clicks/submissions and sharing a timeout across action and page readiness.
- Add Runtime `cache_path` for disk cache/persistent browser storage, following frozen initial configuration rules.
- Add live Python instance/container proxies, binding isolation, and revocation.
- Add `Python.to_value()` to copy Python containers into plain JS Array/Object values.
- Support JS Promise waits, async evaluation/calls, and Python awaitable-to-Promise conversion.
- Add asyncio scheduled driving; await never implicitly calls `Runtime.update()`.
- Clean up waits/listeners on cancellation, unbinding, navigation, closing, and driver failure.
