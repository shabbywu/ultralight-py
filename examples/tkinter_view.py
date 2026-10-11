"""Interactive CPU-rendered page in a Tk Canvas (no extra image dependencies)."""
import argparse
import time
import tkinter as tk

from ultralight_py import Runtime
from ultralight_py.integrations.tkinter import TkInputAdapter

HTML = """
<style>body{margin:16px;font:16px sans-serif;background:#fff;color:#222}
button,input{font:inherit;padding:8px}#scroll{height:200px;overflow:auto;margin-top:16px;border:1px solid #aaa}
#content{height:1200px;width:1200px;background:linear-gradient(#eee,#9cf)}</style>
<button onclick="leftValue.textContent=left.increment()">Left +1</button>: <span id=leftValue>0</span>
<button onclick="rightValue.textContent=right.increment()">Right +1</button>: <span id=rightValue>100</span>
<p><input placeholder="Type here"><span id=typed></span></p>
<div id=scroll><div id=content>Scroll vertically or Shift-scroll horizontally</div></div>
<p id=events>Input events appear here</p>
<script>addEventListener('keydown',e=>events.textContent=`key: ${e.key}, repeat: ${e.repeat}`);
addEventListener('input',e=>typed.textContent=e.target.value);</script>
"""


def ppm(pixels):
    """Copy visible RGB rows; SDK rows may contain padding."""
    rgb = bytearray(pixels.width * pixels.height * 3)
    for y in range(pixels.height):
        row = pixels.data[y * pixels.row_bytes:y * pixels.row_bytes + pixels.width * 4]
        offset = y * pixels.width * 3
        end = offset + pixels.width * 3
        rgb[offset:end:3] = row[2::4]
        rgb[offset + 1:end:3] = row[1::4]
        rgb[offset + 2:end:3] = row[0::4]
    return f"P6\n{pixels.width} {pixels.height}\n255\n".encode() + rgb


class Counter:
    def __init__(self, value):
        self.value = value
        self.history = []

    def increment(self):
        self.value += 1
        self.history.append(self.value)
        return self.value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true", help="Verify display and close automatically")
    args = parser.parse_args()
    root = tk.Tk()
    root.title("Ultralight Python / Tkinter")
    canvas = tk.Canvas(root, width=640, height=480, highlightthickness=0, takefocus=True)
    canvas.pack(fill="both", expand=True)
    runtime = Runtime()
    view = runtime.create_view(640, 480)
    adapter = TkInputAdapter(canvas, view)
    left, right = Counter(0), Counter(100)
    bindings = []

    def bind_models(event):
        if event.is_main_frame:
            bindings[:] = [view.bind_object("left", left), view.bind_object("right", right)]

    view.set_callbacks(window_ready=bind_models)
    view.load_html(HTML)
    item = canvas.create_image(0, 0, anchor="nw")
    state = {"timer": None, "image": None, "closed": False, "frames": 0}
    deadline = time.monotonic() + 5

    def close():
        if state["closed"]:
            return
        state["closed"] = True
        if state["timer"] is not None:
            root.after_cancel(state["timer"])
            state["timer"] = None
        adapter.close()
        for binding in bindings:
            binding.close()
        view.close()
        runtime.close()
        root.destroy()

    def resize(event):
        if event.width > 0 and event.height > 0 and not state["closed"]:
            view.resize(event.width, event.height)

    def tick():
        state["timer"] = None
        if state["closed"]:
            return
        try:
            runtime.update()
            runtime.refresh_display()
            runtime.render()
            image = tk.PhotoImage(data=ppm(view.copy_pixels()), format="PPM", master=root)
            canvas.itemconfigure(item, image=image)
            state["image"] = image
            state["frames"] += 1
            if args.smoke:
                if view.evaluate("document.readyState === 'complete'") and state["frames"] >= 3:
                    assert image.width() == canvas.winfo_width()
                    assert image.height() == canvas.winfo_height()
                    assert image.get(0, 0) == (255, 255, 255)
                    assert canvas.itemcget(item, "image")
                    view.evaluate("document.querySelectorAll('button')[0].click()")
                    assert (left.value, right.value) == (1, 100)
                    assert view.evaluate("leftValue.textContent") == "1"
                    view.evaluate("document.querySelectorAll('button')[1].click()")
                    assert (left.value, right.value) == (1, 101)
                    assert view.evaluate("rightValue.textContent") == "101"
                    assert view.evaluate("left.history") is left.history
                    print("Tk display and Python model isolation smoke passed")
                    close()
                    return
                if time.monotonic() > deadline:
                    raise TimeoutError("Page did not finish loading")
            state["timer"] = root.after(33, tick)
        except BaseException:
            close()
            raise

    def callback_error(kind, value, traceback):
        close()
        raise value.with_traceback(traceback)

    root.report_callback_exception = callback_error
    canvas.bind("<Configure>", resize)
    root.protocol("WM_DELETE_WINDOW", close)
    try:
        tick()
        root.mainloop()
    finally:
        close()


if __name__ == "__main__":
    main()
