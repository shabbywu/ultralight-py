"""Input integration cases run in separate processes (one Renderer per process)."""
import gc
import sys
import threading
import time
import weakref

from ultralight_py import (ErrorCode, KeyCode, KeyEvent, KeyEventType, Modifiers,
                          MouseButton, MouseEvent, MouseEventType, Runtime,
                          ScrollEvent, ScrollEventType, UltralightError)

HTML = """<style>body{margin:0}button,input{display:block;width:150px;height:40px}
#area{position:absolute;top:100px;left:0;width:280px;height:100px;overflow:auto}
#content{width:2000px;height:2000px}</style>
<button id=b>click</button><input id=i><div id=area><div id=content>scroll</div></div>
<script>globalThis.events=[];globalThis.clicks=0;
b.onclick=()=>{clicks++;if(globalThis.host)host()};
for(const name of ['mousemove','mousedown','mouseup','keydown','keyup','input','wheel'])
addEventListener(name,e=>events.push({type:e.type,key:e.key||'',repeat:!!e.repeat,
shift:!!e.shiftKey,ctrl:!!e.ctrlKey,meta:!!e.metaKey,button:e.button===undefined?-1:e.button}));
</script>"""


def frame(runtime):
    runtime.update(); runtime.refresh_display(); runtime.render()


def pump(runtime, ready):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        frame(runtime)
        if ready():
            return
        time.sleep(.005)
    raise AssertionError("Input page timed out")


def page(runtime):
    view = runtime.create_view(320, 240)
    ready = []
    view.set_callbacks(dom_ready=lambda event: ready.append(event) if event.is_main_frame else None)
    view.load_html(HTML)
    pump(runtime, lambda: ready)
    view.set_callbacks()
    return view


def expect(code, callback):
    try:
        callback()
    except UltralightError as error:
        assert error.code == code, error
    else:
        raise AssertionError(f"Expected {code}")


def pointer():
    with Runtime() as runtime:
        view = page(runtime)
        assert view.has_focus
        view.unfocus(); assert not view.has_focus
        view.focus(); assert view.has_focus
        view.click(20, 20)
        view.fire_mouse_event(MouseEvent(MouseEventType.DOWN, 20, 20, MouseButton.LEFT))
        view.fire_mouse_event(MouseEvent(MouseEventType.UP, 20, 20, MouseButton.LEFT))
        assert view.evaluate("clicks") == 2
        view.mouse_down(20, 20)
        view.mouse_move(60, 25, button=MouseButton.LEFT)
        view.mouse_up(60, 25)
        assert view.evaluate("events.some(e=>e.type==='mousemove'&&e.button===0)")
        view.mouse_move(180, 150)
        view.scroll(delta_y=-100, x=180, y=150)
        pump(runtime, lambda: view.evaluate("area.scrollTop>0"))
        view.fire_scroll_event(ScrollEvent(-100, 0, x=180, y=150))
        pump(runtime, lambda: view.evaluate("area.scrollLeft>0"))
        view.fire_scroll_event(ScrollEvent(0, -1, ScrollEventType.PAGE, 180, 150))
        pump(runtime, lambda: view.evaluate("area.scrollTop>100"))
        view.load_html(HTML)
        pump(runtime, lambda: view.evaluate("document.readyState==='complete'"))
        view.click(20, 20)
        assert view.evaluate("clicks") == 1
        view.close()
        for callback in (view.focus, view.unfocus, lambda: view.has_focus,
                         lambda: view.mouse_move(0, 0), lambda: view.scroll()):
            expect(ErrorCode.Closed, callback)


def keyboard():
    with Runtime() as runtime:
        view = page(runtime)
        view.click(20, 65); assert view.has_input_focus
        view.key_down(KeyCode.GK_A)
        assert view.evaluate("i.value") == ""
        view.input_text("a中文🐉")
        view.key_up(KeyCode.GK_A)
        assert view.evaluate("i.value") == "a中文🐉"
        view.fire_key_event(KeyEvent(KeyEventType.RAW_KEY_DOWN, KeyCode.GK_A, modifiers=Modifiers.SHIFT,
                                     is_auto_repeat=True))
        view.fire_key_event(KeyEvent(KeyEventType.CHAR, text="A", unmodified_text="a", modifiers=Modifiers.SHIFT))
        view.key_up(KeyCode.GK_A)
        assert view.evaluate("i.value") == "a中文🐉A"
        assert view.evaluate("events.some(e=>e.type==='keydown'&&e.shift&&e.repeat)")
        view.key_down(KeyCode.GK_SHIFT, modifiers=Modifiers.SHIFT)
        view.mouse_move(20, 65)
        assert view.evaluate("events.at(-1).shift")
        view.key_up(KeyCode.GK_SHIFT)
        view.mouse_move(21, 65)
        assert not view.evaluate("events.at(-1).shift")
        view.key_down(KeyCode.GK_BACK); view.key_up(KeyCode.GK_BACK)
        assert view.evaluate("i.value") == "a中文🐉"
        view.input_text("")
        view.close()
        expect(ErrorCode.Closed, lambda: view.input_text(""))


def guards():
    with Runtime() as runtime:
        view = page(runtime)
        errors = []
        def worker():
            try:
                expect(ErrorCode.WrongThread, lambda: view.click(0, 0))
                expect(ErrorCode.WrongThread, lambda: view.has_focus)
            except BaseException as error:
                errors.append(error)
        thread = threading.Thread(target=worker); thread.start(); thread.join()
        assert not errors, errors
        called = []
        def host():
            called.append(True)
            expect(ErrorCode.Busy, lambda: view.click(20, 20))
            expect(ErrorCode.Busy, runtime.update)
            expect(ErrorCode.Busy, runtime.render)
            assert view.evaluate("clicks") >= 1
        view.bind_function("host", host)
        view.click(20, 20)
        assert called
        # Calling a host function from evaluate also holds a Bridge scope.
        def bridge_host():
            expect(ErrorCode.Busy, view.focus)
        view.bind_function("bridge_host", bridge_host)
        view.evaluate("bridge_host()")
        view.focus(); frame(runtime)
        runtime.set_error_handler(errors.append)
        view.bind_function("host", lambda: (_ for _ in ()).throw(ValueError("input callback failed")))
        view.click(20, 20)
        assert view.evaluate("clicks") >= 2
        # A host exception becomes a JS exception and does not escape dispatch.
        frame(runtime)
        view.focus()


def closing(runtime_close=False):
    runtime = Runtime()
    view = page(runtime)
    called = []
    def close():
        called.append(True)
        runtime.close() if runtime_close else view.close()
    view.bind_function("host", close)
    view.click(20, 20)
    assert called and view.closed
    expect(ErrorCode.Closed, view.focus)
    runtime.close()


def resource_guard():
    attempts = []
    view = None
    def loader(path):
        if path == 'input.html':
            return b'<script src="input.js"></script>'
        if path.endswith('input.js'):
            expect(ErrorCode.Busy, view._native.focus)
            attempts.append(True)
            return b'globalThis.resourceInput=42'
        return None
    with Runtime(resource_loader=loader) as runtime:
        view = runtime.create_view(320, 240)
        ready = []
        view.set_callbacks(dom_ready=lambda event: ready.append(event))
        view.load_url('file:///input.html')
        pump(runtime, lambda: ready)
        assert attempts and view.evaluate('resourceInput') == 42


def tk_window():
    import tkinter as tk
    from ultralight_py.integrations.tkinter import TkInputAdapter
    root = tk.Tk()
    failures = []
    root.report_callback_exception = lambda kind, error, tb: failures.append(error)
    canvas = tk.Canvas(root, width=320, height=240, highlightthickness=0, takefocus=True)
    canvas.pack()
    root.update()
    runtime = Runtime()
    view = page(runtime)
    existing = []
    command = canvas.bind('<Configure>', lambda event: existing.append(True), add='+')
    tags = canvas.bindtags()
    adapter = TkInputAdapter(canvas, view)
    weak = weakref.ref(adapter)
    try:
        canvas.focus_force(); root.update()
        canvas.event_generate('<Motion>', x=20, y=20)
        canvas.event_generate('<ButtonPress-1>', x=20, y=20)
        canvas.event_generate('<ButtonRelease-1>', x=20, y=20)
        root.update(); frame(runtime)
        assert view.evaluate('clicks') == 1
        canvas.event_generate('<ButtonPress-1>', x=20, y=65)
        canvas.event_generate('<ButtonRelease-1>', x=20, y=65)
        canvas.event_generate('<KeyPress>', keysym='a')
        canvas.event_generate('<KeyRelease>', keysym='a')
        root.update(); frame(runtime)
        assert view.evaluate('i.value') == 'a'
        canvas.event_generate('<Motion>', x=180, y=150)
        canvas.event_generate('<MouseWheel>', x=180, y=150, delta=-3)
        pump(runtime, lambda: view.evaluate('area.scrollTop>0'))
        adapter.close(); adapter.close()
        assert canvas.bindtags() == tags
        assert command in canvas.bind('<Configure>')
        del adapter; gc.collect(); assert weak() is None
        # Automatic detach while Tcl is destroying the widget must not leave
        # callback names in the root's command list or keep the View alive.
        second = TkInputAdapter(canvas, view)
        second_weak = weakref.ref(second)
        canvas.destroy(); del second; gc.collect()
        assert second_weak() is None and not view.closed
        assert not failures, failures
    finally:
        if weak() is not None:
            weak().close()
        runtime.close()
        root.destroy()


if __name__ == '__main__':
    {'pointer': pointer, 'keyboard': keyboard, 'guards': guards,
     'close_view': closing, 'close_runtime': lambda: closing(True),
     'resource_guard': resource_guard, 'tk_window': tk_window}[sys.argv[1]]()
