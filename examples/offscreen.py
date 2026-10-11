"""Load HTML, evaluate JavaScript, and read a CPU frame without a window."""

import time
from ultralight_py import Runtime

with Runtime() as runtime:
    with runtime.create_view(320, 180) as view:
        ready, failures = [], []
        view.set_callbacks(
            dom_ready=lambda event: ready.append(event) if event.is_main_frame else None,
            fail_loading=failures.append,
        )
        view.load_html(
            "<style>html,body{margin:0;background:#e04020}</style><body>Hello Ultralight"
        )
        deadline = time.monotonic() + 5
        while not ready:
            if failures:
                raise RuntimeError(failures[0].description)
            if time.monotonic() >= deadline:
                raise TimeoutError("Page did not become ready")
            runtime.update()
            runtime.refresh_display()
            runtime.render()
            time.sleep(0.005)
        print(view.evaluate("document.body.textContent"))
        pixels = view.copy_pixels()
        print(pixels.width, pixels.height, pixels.row_bytes, pixels.format)
        print("First BGRA pixel:", list(pixels.data[:4]))
        view.clear_dirty_bounds()
