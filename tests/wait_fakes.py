"""Fake native objects exercising the real Python ownership and wait layers."""

import weakref
from types import SimpleNamespace

from ultralight_py import ErrorCode, Runtime, View, _native


class NativeView:
    def __init__(self):
        self.closed = False
        self.callbacks = {}
        self.is_settled = False
        self.begin_inline = True

    def _check(self):
        if self.closed:
            raise _native._make_error(ErrorCode.Closed, "View is closed")

    def set_callbacks(self, callbacks):
        self.callbacks = callbacks

    def emit(self, name, *, main=True, url="https://example.test"):
        event = SimpleNamespace(is_main_frame=main, frame_id=1, url=url)
        if name == "page_settled":
            self.is_settled = True
            event = url
        self.callbacks[name](event)

    def load_html(self, html, url=""):
        self.is_settled = False
        if self.begin_inline:
            self.emit("begin_loading", url=url)

    def load_url(self, url):
        self.load_html("", url)

    def close(self):
        self.closed = True
        self.callbacks = {}

    def _defer_close(self):
        self.close()


class NativeRuntime:
    def __init__(self):
        self.closed = False
        self.updates = self.renders = 0
        self.refreshes = []
        self.on_update = lambda: None
        self.on_render = lambda: None
        self.views = []

    def create_view(self, *args):
        view = NativeView()
        self.views.append(view)
        return view

    def update(self):
        self.updates += 1
        self.on_update()

    def refresh_display(self, display_id):
        self.refreshes.append(display_id)

    def render(self):
        self.renders += 1
        self.on_render()

    def set_error_handler(self, callback):
        self.error_handler = callback

    def close(self):
        self.closed = True
        for view in self.views:
            view.close()


def runtime():
    result = object.__new__(Runtime)
    result._native = NativeRuntime()
    result._views = weakref.WeakSet()
    result._sessions = {}
    result._updating = False
    result.errors = []
    result._error_handler = result.errors.append
    result._resource_loader = None
    return result


def view(runtime):
    return View(runtime._native.create_view(), runtime)
