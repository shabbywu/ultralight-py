"""Input integration cases run in separate processes (one Renderer per process)."""
import gc
import sys
import threading
import time
import weakref

from ultralight_py import (ErrorCode,
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



if __name__ == '__main__':
    pointer()
