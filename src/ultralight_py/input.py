"""Framework-independent input data and script conveniences."""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum, IntFlag

from ultralight_py import _native
from ultralight_py import _support
from ultralight_py import _validation


class MouseEventType(IntEnum):
    MOVE = 0
    DOWN = 1
    UP = 2


class MouseButton(IntEnum):
    NONE = 0
    LEFT = 1
    MIDDLE = 2
    RIGHT = 3
    BACK = 4
    FORWARD = 5


class ScrollEventType(IntEnum):
    PIXEL = 0
    PAGE = 1


class KeyEventType(IntEnum):
    KEY_DOWN = 0  # Legacy combined key/text event; prefer RAW_KEY_DOWN + CHAR.
    KEY_UP = 1
    RAW_KEY_DOWN = 2
    CHAR = 3


class Modifiers(IntFlag):
    NONE = 0
    ALT = 1
    CTRL = 2
    META = 4
    SHIFT = 8


KeyCode = IntEnum("KeyCode", dict(_native._key_codes), module=__name__)


def _enum(value, kind) -> None:
    if not isinstance(value, kind):
        raise TypeError(f"Expected {kind.__name__}")


def _modifiers(value: Modifiers) -> None:
    _enum(value, Modifiers)
    if int(value) & ~15:
        raise ValueError("Unknown modifier bits")


@dataclass(frozen=True)
class MouseEvent:
    type: MouseEventType
    x: int
    y: int
    button: MouseButton = MouseButton.NONE

    def __post_init__(self):
        _enum(self.type, MouseEventType)
        _enum(self.button, MouseButton)
        _validation.integer(self.x, "x")
        _validation.integer(self.y, "y")
        if self.type != MouseEventType.MOVE and self.button == MouseButton.NONE:
            raise ValueError("Mouse down/up requires a button")


@dataclass(frozen=True)
class ScrollEvent:
    delta_x: int
    delta_y: int
    type: ScrollEventType = ScrollEventType.PIXEL
    x: int = -1
    y: int = -1

    def __post_init__(self):
        _enum(self.type, ScrollEventType)
        for name in ("delta_x", "delta_y", "x", "y"):
            _validation.integer(getattr(self, name), name)


@dataclass(frozen=True)
class KeyEvent:
    type: KeyEventType
    virtual_key_code: int = 0
    native_key_code: int = 0
    modifiers: Modifiers = Modifiers.NONE
    key_identifier: str | None = None
    text: str = ""
    unmodified_text: str = ""
    is_keypad: bool = False
    is_auto_repeat: bool = False
    is_system_key: bool = False

    def __post_init__(self):
        _enum(self.type, KeyEventType)
        _modifiers(self.modifiers)
        _validation.integer(self.virtual_key_code, "virtual_key_code")
        _validation.integer(self.native_key_code, "native_key_code")
        if self.key_identifier is not None and not isinstance(self.key_identifier, str):
            raise TypeError("key_identifier must be str or None")
        for name in ("text", "unmodified_text"):
            if not isinstance(getattr(self, name), str):
                raise TypeError(f"{name} must be str")
        for name in ("is_keypad", "is_auto_repeat", "is_system_key"):
            if not isinstance(getattr(self, name), bool):
                raise TypeError(f"{name} must be bool")


class InputView:
    """Input methods shared by the public View, with no window-framework state."""

    def _input_call(self, name, *args):
        return _support.call(getattr(self._native, name), *args)

    def fire_mouse_event(self, event: MouseEvent) -> None:
        if not isinstance(event, MouseEvent):
            raise TypeError("event must be MouseEvent")
        self._input_call("fire_mouse_event", int(event.type), event.x, event.y, int(event.button))

    def fire_scroll_event(self, event: ScrollEvent) -> None:
        if not isinstance(event, ScrollEvent):
            raise TypeError("event must be ScrollEvent")
        self._input_call("fire_scroll_event", int(event.type), event.delta_x, event.delta_y, event.x, event.y)

    def fire_key_event(self, event: KeyEvent) -> None:
        if not isinstance(event, KeyEvent):
            raise TypeError("event must be KeyEvent")
        self._input_call("fire_key_event", int(event.type), int(event.modifiers), event.virtual_key_code,
                         event.native_key_code, event.key_identifier, event.text, event.unmodified_text,
                         event.is_keypad, event.is_auto_repeat, event.is_system_key)

    def focus(self) -> None:
        self._input_call("focus")

    def unfocus(self) -> None:
        self._input_call("unfocus")

    @property
    def has_focus(self) -> bool:
        return _support.call(lambda: self._native.has_focus)

    @property
    def has_input_focus(self) -> bool:
        return _support.call(lambda: self._native.has_input_focus)

    def mouse_move(self, x: int, y: int, *, button: MouseButton = MouseButton.NONE) -> None:
        self.fire_mouse_event(MouseEvent(MouseEventType.MOVE, x, y, button))

    def mouse_down(self, x: int, y: int, *, button: MouseButton = MouseButton.LEFT) -> None:
        self.fire_mouse_event(MouseEvent(MouseEventType.DOWN, x, y, button))

    def mouse_up(self, x: int, y: int, *, button: MouseButton = MouseButton.LEFT) -> None:
        self.fire_mouse_event(MouseEvent(MouseEventType.UP, x, y, button))

    def click(self, x: int, y: int, *, button: MouseButton = MouseButton.LEFT) -> None:
        # Validate the whole sequence before its first side effect.
        down = MouseEvent(MouseEventType.DOWN, x, y, button)
        self.mouse_move(x, y)
        self.fire_mouse_event(down)
        self.mouse_up(x, y, button=button)

    def scroll(self, delta_x: int = 0, delta_y: int = 0, *, type: ScrollEventType = ScrollEventType.PIXEL,
               x: int = -1, y: int = -1) -> None:
        self.fire_scroll_event(ScrollEvent(delta_x, delta_y, type, x, y))

    def key_down(self, virtual_key_code: int, *, modifiers: Modifiers = Modifiers.NONE,
                 native_key_code: int = 0, is_keypad: bool = False, is_auto_repeat: bool = False) -> None:
        self.fire_key_event(KeyEvent(KeyEventType.RAW_KEY_DOWN, virtual_key_code, native_key_code, modifiers,
                                    is_keypad=is_keypad, is_auto_repeat=is_auto_repeat))

    def key_up(self, virtual_key_code: int, *, modifiers: Modifiers = Modifiers.NONE,
               native_key_code: int = 0, is_keypad: bool = False) -> None:
        self.fire_key_event(KeyEvent(KeyEventType.KEY_UP, virtual_key_code, native_key_code, modifiers,
                                    is_keypad=is_keypad))

    def input_text(self, text: str, *, modifiers: Modifiers = Modifiers.NONE) -> None:
        if not isinstance(text, str):
            raise TypeError("text must be str")
        _modifiers(modifiers)
        # Even an empty string must honor thread/closed/resource-callback checks.
        self._input_call("_check_input")
        for character in text:
            self.fire_key_event(KeyEvent(KeyEventType.CHAR, modifiers=modifiers,
                                         text=character, unmodified_text=character))
