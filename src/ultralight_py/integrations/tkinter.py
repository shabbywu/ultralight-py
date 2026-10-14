"""Tk input translation. Rendering and Runtime/View ownership stay with the host."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from dataclasses import replace

from ultralight_py import ErrorCode, UltralightError, _support, _validation
from ultralight_py.api import View
from ultralight_py.input import KeyCode, KeyEvent, KeyEventType, Modifiers, MouseButton

_KEYS = {
    "BackSpace": "BACK",
    "Tab": "TAB",
    "ISO_Left_Tab": "TAB",
    "Return": "RETURN",
    "Escape": "ESCAPE",
    "space": "SPACE",
    "Prior": "PRIOR",
    "Next": "NEXT",
    "Home": "HOME",
    "End": "END",
    "Left": "LEFT",
    "Right": "RIGHT",
    "Up": "UP",
    "Down": "DOWN",
    "Insert": "INSERT",
    "Delete": "DELETE",
    "Caps_Lock": "CAPITAL",
    "Num_Lock": "NUMLOCK",
    "Scroll_Lock": "SCROLL",
    "Pause": "PAUSE",
    "Print": "SNAPSHOT",
    "Shift_L": "LSHIFT",
    "Shift_R": "RSHIFT",
    "Control_L": "LCONTROL",
    "Control_R": "RCONTROL",
    "Alt_L": "LMENU",
    "Alt_R": "RMENU",
    "Option_L": "LMENU",
    "Option_R": "RMENU",
    "Meta_L": "LWIN",
    "Meta_R": "RWIN",
    "Super_L": "LWIN",
    "Super_R": "RWIN",
    "Command": "LWIN",
    "Menu": "APPS",
    "KP_Enter": "RETURN",
    "KP_Add": "ADD",
    "KP_Subtract": "SUBTRACT",
    "KP_Multiply": "MULTIPLY",
    "KP_Divide": "DIVIDE",
    "KP_Decimal": "DECIMAL",
    "KP_Separator": "SEPARATOR",
    "semicolon": "OEM_1",
    "colon": "OEM_1",
    "equal": "OEM_PLUS",
    "plus": "OEM_PLUS",
    "comma": "OEM_COMMA",
    "less": "OEM_COMMA",
    "minus": "OEM_MINUS",
    "underscore": "OEM_MINUS",
    "period": "OEM_PERIOD",
    "greater": "OEM_PERIOD",
    "slash": "OEM_2",
    "question": "OEM_2",
    "grave": "OEM_3",
    "asciitilde": "OEM_3",
    "bracketleft": "OEM_4",
    "braceleft": "OEM_4",
    "backslash": "OEM_5",
    "bar": "OEM_5",
    "bracketright": "OEM_6",
    "braceright": "OEM_6",
    "apostrophe": "OEM_7",
    "quotedbl": "OEM_7",
}
_KEYSYM_TEXT = {
    "space": " ",
    "semicolon": ";",
    "colon": ":",
    "equal": "=",
    "plus": "+",
    "comma": ",",
    "less": "<",
    "minus": "-",
    "underscore": "_",
    "period": ".",
    "greater": ">",
    "slash": "/",
    "question": "?",
    "grave": "`",
    "asciitilde": "~",
    "bracketleft": "[",
    "braceleft": "{",
    "backslash": "\\",
    "bar": "|",
    "bracketright": "]",
    "braceright": "}",
    "apostrophe": "'",
    "quotedbl": '"',
}
_SHIFTED_DIGITS = dict(
    zip(
        [
            "exclam",
            "at",
            "numbersign",
            "dollar",
            "percent",
            "asciicircum",
            "ampersand",
            "asterisk",
            "parenleft",
            "parenright",
        ],
        "1234567890",
    )
)
_MOD_KEYS = {
    "LSHIFT": Modifiers.SHIFT,
    "RSHIFT": Modifiers.SHIFT,
    "LCONTROL": Modifiers.CTRL,
    "RCONTROL": Modifiers.CTRL,
    "LMENU": Modifiers.ALT,
    "RMENU": Modifiers.ALT,
    "LWIN": Modifiers.META,
    "RWIN": Modifiers.META,
}


def _key_code(keysym: str) -> KeyCode:
    name = _KEYS.get(keysym)
    if name is None and len(keysym) == 1 and keysym.isascii() and keysym.isalnum():
        name = keysym.upper()
    if name is None and keysym in _SHIFTED_DIGITS:
        name = _SHIFTED_DIGITS[keysym]
    if (
        name is None
        and keysym.startswith("F")
        and keysym[1:].isdigit()
        and 1 <= int(keysym[1:]) <= 24
    ):
        name = keysym
    if name is None and keysym.startswith("KP_"):
        tail = keysym[3:]
        name = "NUMPAD" + tail if tail.isdigit() and len(tail) == 1 else _KEYS.get(tail)
    return getattr(KeyCode, "GK_" + (name or "UNKNOWN"), KeyCode.GK_UNKNOWN)


class TkInputAdapter:
    """Attach input to a widget; call close() before releasing its borrowed View.

    Coordinates default to 1:1 logical View pixels. wheel_pixels sets the scroll
    distance per wheel unit. Only this adapter's bindings are removed on close.
    """

    def __init__(
        self,
        widget: tk.Misc,
        view: View,
        *,
        coordinate_transform: Callable[[int, int], tuple[int, int]] | None = None,
        wheel_pixels: int = 40,
    ):
        _support.ensure_in_main_thread()
        if coordinate_transform is not None and not callable(coordinate_transform):
            raise TypeError("coordinate_transform must be callable or None")
        _validation.integer(wheel_pixels, "wheel_pixels")
        if wheel_pixels <= 0:
            raise ValueError("wheel_pixels must be positive")
        self._widget = widget
        self._view = view
        self._command_owner = widget._root()
        self._transform = coordinate_transform
        self._wheel_pixels = wheel_pixels
        self._system = str(widget.tk.call("tk", "windowingsystem"))
        self._tag = f"UltralightInput_{id(self)}"
        self._bindings: list[tuple[str, str]] = []
        self._keys: dict[int, KeyEvent] = {}
        self._buttons: dict[MouseButton, tuple[int, int]] = {}
        self._pending: dict[int, tuple[str, int, KeyEvent]] = {}
        self._wheel_remainder = [0.0, 0.0]
        self._closed = False
        events = {
            "<Motion>": self._motion,
            "<ButtonPress>": self._button_down,
            "<ButtonRelease>": self._button_up,
            "<MouseWheel>": self._wheel,
            "<KeyPress>": self._key_press,
            "<KeyRelease>": self._key_release,
            "<FocusIn>": self._focus_in,
            "<FocusOut>": self._focus_out,
            "<Destroy>": self._destroy,
        }
        try:
            for sequence, callback in events.items():
                command = widget.bind_class(self._tag, sequence, self._handler(callback))
                self._bindings.append((sequence, command))
            widget.bindtags((self._tag,) + tuple(widget.bindtags()))
        except BaseException:
            self.close()
            raise

    def _handler(self, callback):
        def invoke(event):
            if self._closed:
                return None
            if self._view.closed:
                self.close()
                return None
            try:
                return callback(event)
            except UltralightError as error:
                if error.code == ErrorCode.Closed:
                    self.close()
                    return None
                raise

        return invoke

    def _coordinates(self, event):
        x, y = event.x, event.y
        return (x, y) if self._transform is None else self._transform(x, y)

    def _modifiers(self, state):
        result = Modifiers.NONE
        masks = (
            (1, Modifiers.SHIFT),
            (4, Modifiers.CTRL),
            (16 if self._system == "aqua" else 8, Modifiers.ALT),
            (8 if self._system == "aqua" else 64, Modifiers.META),
        )
        for mask, modifier in masks:
            if state & mask:
                result |= modifier
        return result

    def _button(self, number):
        if self._system == "aqua":
            return {
                1: MouseButton.LEFT,
                2: MouseButton.RIGHT,
                3: MouseButton.MIDDLE,
                8: MouseButton.BACK,
                9: MouseButton.FORWARD,
            }.get(number)
        return {
            1: MouseButton.LEFT,
            2: MouseButton.MIDDLE,
            3: MouseButton.RIGHT,
            8: MouseButton.BACK,
            9: MouseButton.FORWARD,
        }.get(number)

    def _motion(self, event):
        button = next(reversed(self._buttons), MouseButton.NONE)
        x, y = self._coordinates(event)
        for pressed in self._buttons:
            self._buttons[pressed] = (x, y)
        self._view.mouse_move(x, y, button=button)
        return "break"

    def _button_down(self, event):
        if self._system == "x11" and event.num in (4, 5):
            self._scroll(event, 1 if event.num == 4 else -1)
            return "break"
        button = self._button(event.num)
        if button is None:
            return None
        self._widget.focus_set()
        x, y = self._coordinates(event)
        self._buttons[button] = (x, y)
        self._view.mouse_down(x, y, button=button)
        return "break"

    def _button_up(self, event):
        button = self._button(event.num)
        if button is None:
            return "break" if self._system == "x11" and event.num in (4, 5) else None
        self._buttons.pop(button, None)
        self._view.mouse_up(*self._coordinates(event), button=button)
        return "break"

    def _scroll(self, event, units):
        axis = 0 if event.state & 1 else 1
        self._wheel_remainder[axis] += units * self._wheel_pixels
        delta = int(self._wheel_remainder[axis])
        self._wheel_remainder[axis] -= delta
        if delta:
            x, y = self._coordinates(event)
            self._view.scroll(
                delta_x=delta if axis == 0 else 0, delta_y=delta if axis == 1 else 0, x=x, y=y
            )

    def _wheel(self, event):
        self._scroll(event, event.delta / 120 if self._system == "win32" else event.delta)
        return "break"

    def _key(self, event, type):
        key = _key_code(event.keysym)
        modifiers = self._modifiers(event.state)
        own = _MOD_KEYS.get(key.name.removeprefix("GK_"), Modifiers.NONE)
        if type == KeyEventType.RAW_KEY_DOWN:
            modifiers |= own
        else:
            modifiers &= ~own
            for native, pressed in self._keys.items():
                if native != event.keycode:
                    modifiers |= _MOD_KEYS.get(
                        pressed.virtual_key_code.name.removeprefix("GK_"), Modifiers.NONE
                    )
        text = event.char if isinstance(event.char, str) and event.char != "??" else ""
        unmodified = (
            event.keysym if len(event.keysym) == 1 else _KEYSYM_TEXT.get(event.keysym, text)
        )
        return KeyEvent(
            type,
            key,
            event.keycode,
            modifiers,
            text=text,
            unmodified_text=unmodified,
            is_keypad=event.keysym.startswith("KP_"),
        )

    def _key_press(self, event):
        pending = self._pending.pop(event.keycode, None)
        if pending:
            self._widget.after_cancel(pending[0])
            if pending[1] != event.time:
                self._release(event.keycode, pending[2])
                if self._closed:
                    return "break"
        key = self._key(event, KeyEventType.RAW_KEY_DOWN)
        key = replace(key, is_auto_repeat=event.keycode in self._keys)
        self._keys[event.keycode] = key
        view = self._view
        view.fire_key_event(key)
        if self._closed or view.closed:
            return "break"
        text = key.text
        shortcut = key.modifiers & Modifiers.META or (
            key.modifiers & Modifiers.CTRL and not key.modifiers & Modifiers.ALT
        )
        if text and not shortcut and (text.isprintable() or text in ("\r", "\n")):
            self._view.fire_key_event(replace(key, type=KeyEventType.CHAR))
        return "break"

    def _release(self, native, key):
        self._keys.pop(native, None)
        if not self._closed and not self._view.closed:
            self._view.fire_key_event(key)

    def _key_release(self, event):
        key = self._key(event, KeyEventType.KEY_UP)
        if self._system == "x11":
            previous = self._pending.pop(event.keycode, None)
            if previous:
                self._widget.after_cancel(previous[0])

            def release():
                self._pending.pop(event.keycode, None)
                self._release(event.keycode, key)

            token = self._widget.after_idle(release)
            self._pending[event.keycode] = (token, event.time, key)
        else:
            self._release(event.keycode, key)
        return "break"

    def _focus_in(self, event):
        self._view.focus()

    def _focus_out(self, event):
        view = self._view
        self._cancel_pending()
        for native, key in list(self._keys.items()):
            self._release(
                native,
                replace(
                    key,
                    type=KeyEventType.KEY_UP,
                    modifiers=Modifiers.NONE,
                    text="",
                    unmodified_text="",
                ),
            )
        for button, (x, y) in list(self._buttons.items()):
            if not view.closed and not self._closed:
                view.mouse_up(x, y, button=button)
        self._buttons.clear()
        if not view.closed and not self._closed:
            view.unfocus()

    def _destroy(self, event):
        if event.widget is self._widget:
            self.close()

    def _cancel_pending(self):
        for token, _, _ in self._pending.values():
            self._widget.after_cancel(token)
        self._pending.clear()

    def close(self) -> None:
        _support.ensure_in_main_thread()
        if self._closed:
            return
        self._closed = True
        self._cancel_pending()
        try:
            self._widget.bindtags(tuple(tag for tag in self._widget.bindtags() if tag != self._tag))
        except tk.TclError:
            pass  # Destroy events arrive while a widget is already being removed.
        for sequence, command in self._bindings:
            self._widget.unbind_class(self._tag, sequence)
            self._command_owner.deletecommand(command)
        self._bindings.clear()
        self._keys.clear()
        self._buttons.clear()
        self._view = self._widget = self._transform = self._command_owner = None
