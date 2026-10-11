"""Window-independent tests for Tk's platform-specific input translation."""

import gc
from types import SimpleNamespace
import weakref

import pytest

pytest.importorskip("tkinter")
from ultralight_py import KeyCode, KeyEventType, Modifiers, MouseButton
from ultralight_py.integrations.tkinter import TkInputAdapter, _key_code


class Widget:
    def __init__(self, system):
        self.tk = SimpleNamespace(call=lambda *args: system)
        self.tags = ("widget", "Canvas", "root", "all")
        self.callbacks = {}
        self.commands = {}
        self.timers = {}
        self.focused = False

    def _root(self):
        return self

    def bindtags(self, tags=None):
        if tags is not None:
            self.tags = tags
        return self.tags

    def bind_class(self, tag, sequence, callback):
        token = "command" + str(len(self.commands))
        self.commands[token] = callback
        self.callbacks[(tag, sequence)] = callback
        return token

    def unbind_class(self, tag, sequence):
        del self.callbacks[(tag, sequence)]

    def deletecommand(self, token):
        del self.commands[token]

    def focus_set(self):
        self.focused = True

    def after_idle(self, callback):
        token = "timer" + str(len(self.timers))
        self.timers[token] = callback
        return token

    def after_cancel(self, token):
        self.timers.pop(token, None)

    def dispatch(self, sequence, **kwargs):
        event = SimpleNamespace(
            x=10,
            y=20,
            state=0,
            delta=0,
            num=1,
            char="",
            keysym="a",
            keycode=38,
            time=1,
            widget=self,
        )
        event.__dict__.update(kwargs)
        return self.callbacks[(self.tags[0], sequence)](event)

    def idle(self):
        timers, self.timers = self.timers, {}
        for callback in timers.values():
            callback()


class View:
    closed = False

    def __init__(self):
        self.events = []

    def __getattr__(self, name):
        return lambda *args, **kwargs: self.events.append((name, args, kwargs))


def test_cleanup_preserves_host_tags_and_releases_references():
    widget, view = Widget("aqua"), View()
    adapter = TkInputAdapter(widget, view)
    ref = weakref.ref(adapter)
    widget.bindtags(("later-host-tag",) + widget.bindtags())
    adapter.close()
    adapter.close()
    assert widget.tags == ("later-host-tag", "widget", "Canvas", "root", "all")
    assert not widget.commands and not widget.callbacks
    del adapter
    gc.collect()
    assert ref() is None
    assert not view.closed


@pytest.mark.parametrize(
    "system,number,button",
    [
        ("aqua", 2, MouseButton.RIGHT),
        ("aqua", 3, MouseButton.MIDDLE),
        ("win32", 2, MouseButton.MIDDLE),
        ("x11", 3, MouseButton.RIGHT),
    ],
)
def test_buttons_coordinates_and_drag(system, number, button):
    widget, view = Widget(system), View()
    adapter = TkInputAdapter(widget, view, coordinate_transform=lambda x, y: (x // 2, y // 2))
    widget.dispatch("<ButtonPress>", num=number)
    widget.dispatch("<Motion>", x=-10, y=100)
    widget.dispatch("<ButtonRelease>", num=number)
    assert widget.focused
    assert view.events == [
        ("mouse_down", (5, 10), {"button": button}),
        ("mouse_move", (-5, 50), {"button": button}),
        ("mouse_up", (5, 10), {"button": button}),
    ]
    adapter.close()


@pytest.mark.parametrize(
    "system,sequence,kwargs,expected",
    [
        ("aqua", "<MouseWheel>", {"delta": -2}, (0, -80)),
        ("aqua", "<MouseWheel>", {"delta": 1, "state": 1}, (40, 0)),
        ("win32", "<MouseWheel>", {"delta": -120}, (0, -40)),
        ("x11", "<ButtonPress>", {"num": 4}, (0, 40)),
        ("x11", "<ButtonPress>", {"num": 5, "state": 1}, (-40, 0)),
    ],
)
def test_wheel_normalization(system, sequence, kwargs, expected):
    widget, view = Widget(system), View()
    adapter = TkInputAdapter(widget, view)
    widget.dispatch(sequence, **kwargs)
    assert view.events == [
        ("scroll", (), {"delta_x": expected[0], "delta_y": expected[1], "x": 10, "y": 20})
    ]
    adapter.close()


def test_fractional_wheel_accumulates():
    widget, view = Widget("win32"), View()
    adapter = TkInputAdapter(widget, view)
    for _ in range(3):
        widget.dispatch("<MouseWheel>", delta=1)
    assert view.events[-1][2]["delta_y"] == 1
    adapter.close()


@pytest.mark.parametrize(
    "system,state,modifiers",
    [
        ("aqua", 8, Modifiers.META),
        ("aqua", 16, Modifiers.ALT),
        ("win32", 8, Modifiers.ALT),
        ("x11", 64, Modifiers.META),
    ],
)
def test_modifiers(system, state, modifiers):
    widget, view = Widget(system), View()
    adapter = TkInputAdapter(widget, view)
    widget.dispatch("<KeyPress>", state=state)
    assert view.events[-1][1][0].modifiers == modifiers
    adapter.close()


def test_key_text_repeat_shortcuts_and_shift_release():
    widget, view = Widget("aqua"), View()
    adapter = TkInputAdapter(widget, view)
    widget.dispatch("<KeyPress>", char="a")
    widget.dispatch("<KeyPress>", char="a")
    keys = [entry[1][0] for entry in view.events]
    assert [event.type for event in keys] == [KeyEventType.RAW_KEY_DOWN, KeyEventType.CHAR] * 2
    assert not keys[0].is_auto_repeat and keys[2].is_auto_repeat
    widget.dispatch("<KeyRelease>")
    assert view.events[-1][1][0].type == KeyEventType.KEY_UP
    before = len(view.events)
    widget.dispatch("<KeyPress>", char="\x01", state=4)
    assert len(view.events) == before + 1
    widget.dispatch("<KeyPress>", keysym="Shift_L", keycode=50, state=0)
    assert view.events[-1][1][0].modifiers & Modifiers.SHIFT
    widget.dispatch("<KeyRelease>", keysym="Shift_L", keycode=50, state=1)
    assert not view.events[-1][1][0].modifiers & Modifiers.SHIFT
    adapter.close()


def test_x11_repeat_focus_loss_and_pending_cleanup():
    widget, view = Widget("x11"), View()
    adapter = TkInputAdapter(widget, view)
    widget.dispatch("<KeyPress>", char="a")
    widget.dispatch("<KeyRelease>", time=10)
    widget.dispatch("<KeyPress>", char="a", time=10)
    assert not widget.timers
    assert view.events[-1][1][0].is_auto_repeat
    assert not any(event[1][0].type == KeyEventType.KEY_UP for event in view.events)
    widget.dispatch("<ButtonPress>")
    widget.dispatch("<KeyRelease>", time=11)
    widget.dispatch("<FocusOut>")
    assert not widget.timers
    assert any(entry[0] == "mouse_up" for entry in view.events)
    assert view.events[-1][0] == "unfocus"
    adapter.close()
    assert not widget.timers


def test_idle_release_and_destroy():
    widget, view = Widget("x11"), View()
    adapter = TkInputAdapter(widget, view)
    widget.dispatch("<KeyPress>")
    widget.dispatch("<KeyRelease>")
    widget.idle()
    assert view.events[-1][1][0].type == KeyEventType.KEY_UP
    widget.dispatch("<KeyRelease>")
    widget.dispatch("<Destroy>")
    assert not widget.timers and not widget.commands
    assert not view.closed
    adapter.close()


@pytest.mark.parametrize(
    "keysym,code",
    [
        ("a", "A"),
        ("1", "1"),
        ("exclam", "1"),
        ("F24", "F24"),
        ("KP_7", "NUMPAD7"),
        ("KP_Enter", "RETURN"),
        ("semicolon", "OEM_1"),
        ("中", "UNKNOWN"),
    ],
)
def test_key_mapping(keysym, code):
    assert _key_code(keysym) == getattr(KeyCode, "GK_" + code)


def test_key_callback_can_detach_without_followup_char():
    widget, view = Widget("aqua"), View()
    adapter = TkInputAdapter(widget, view)

    def dispatch(key):
        view.events.append(key)
        adapter.close()

    view.fire_key_event = dispatch
    widget.dispatch("<KeyPress>", char="a")
    assert len(view.events) == 1
    assert not widget.commands


def test_focus_loss_releases_button_at_latest_drag_position():
    widget, view = Widget("aqua"), View()
    adapter = TkInputAdapter(widget, view)
    widget.dispatch("<ButtonPress>")
    widget.dispatch("<Motion>", x=99, y=-20)
    widget.dispatch("<FocusOut>")
    assert ("mouse_up", (99, -20), {"button": MouseButton.LEFT}) in view.events
    adapter.close()


def test_shortcut_preserves_unmodified_text():
    widget, view = Widget("aqua"), View()
    adapter = TkInputAdapter(widget, view)
    widget.dispatch("<KeyPress>", char="\x01", state=4, keysym="a")
    key = view.events[-1][1][0]
    assert key.text == "\x01" and key.unmodified_text == "a"
    adapter.close()
