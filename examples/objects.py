"""Two Python instances, live containers and independent binding revocation."""

import time

from ultralight_py import JavaScriptError, Runtime


class Counter:
    def __init__(self, value):
        self.value = value
        self.history = []

    def increment(self, amount=1):
        self.value += amount
        self.history.append(self.value)
        return self.value


with Runtime() as runtime, runtime.create_view(320, 180) as view:
    left, right = Counter(0), Counter(100)
    ready = []
    bindings = []

    def window_ready(event):
        if event.is_main_frame:
            bindings[:] = [view.bind_object("left", left), view.bind_object("right", right)]

    view.set_callbacks(
        window_ready=window_ready,
        dom_ready=lambda event: ready.append(event) if event.is_main_frame else None,
    )
    view.load_html("""<script>
            left.increment(2);
            Python.call(right.increment, [], {amount: 3});
            left.history.push(9);
            window.savedLeft = left;
            window.output = [...left.history];
        </script><body>Python objects</body>""")
    deadline = time.monotonic() + 5
    while not ready:
        if time.monotonic() > deadline:
            raise TimeoutError("Page did not become ready")
        runtime.update()
        runtime.refresh_display()
        runtime.render()
        time.sleep(0.005)
    assert (left.value, right.value) == (2, 103)
    assert view.evaluate("left.history") is left.history
    assert view.evaluate("output") == [2, 9]
    bindings[0].close()
    try:
        view.evaluate("savedLeft.value")
    except JavaScriptError:
        pass
    else:
        raise AssertionError("Revoked proxy remained accessible")
    assert view.evaluate("right.increment()") == 104
    print("Instance isolation, live containers and revocation passed")
