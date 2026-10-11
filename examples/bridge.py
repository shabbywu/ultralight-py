"""Bind Python before page scripts run, and call JavaScript with a receiver."""

import time
from ultralight_py import Runtime

with Runtime() as runtime:
    with runtime.create_view(320, 180) as view:
        ready = []

        def window_ready(event):
            if event.is_main_frame:
                view.bind_function("python_add", lambda a, b: a + b)

        view.set_callbacks(
            window_ready=window_ready,
            dom_ready=lambda event: ready.append(event) if event.is_main_frame else None,
        )
        view.load_html("<script>window.answer=python_add(20,22)</script><body>Bridge")
        deadline = time.monotonic() + 5
        while not ready:
            if time.monotonic() >= deadline:
                raise TimeoutError("Page did not become ready")
            runtime.update()
            time.sleep(0.005)
        print("Python result:", view.evaluate("answer"))
        with view.evaluate_handle("({offset:10, add(n){return this.offset+n}})") as receiver:
            with receiver.get("add") as function:
                with function.call(5, this=receiver) as result:
                    print("JS result:", result.to_python())
