"""Serve an in-memory page and JavaScript through Python's resource loader."""

import time

from ultralight_py import Resource, Runtime

resources = {
    "page.html": Resource(b'<script src="app.js"></script><body>Virtual resources', "text/html"),
    "app.js": Resource(b"window.answer=42", "application/javascript"),
}

with Runtime(resource_loader=resources.get) as runtime, runtime.create_view(320, 180) as view:
    ready, failures = [], []
    view.set_callbacks(
        dom_ready=lambda event: ready.append(event) if event.is_main_frame else None,
        fail_loading=failures.append,
    )
    view.load_url("file:///page.html")
    deadline = time.monotonic() + 5
    while not ready:
        if failures:
            raise RuntimeError(failures[0].description)
        if time.monotonic() >= deadline:
            raise TimeoutError("Page did not become ready")
        runtime.update()
        time.sleep(0.005)
    print(view.evaluate("answer"))
