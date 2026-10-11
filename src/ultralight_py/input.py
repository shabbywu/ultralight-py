"""Framework-independent input data and script conveniences."""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum



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








def _integer(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if not -(2**31) <= value < 2**31:
        raise OverflowError(f"{name} exceeds the SDK int range")


def _enum(value, kind) -> None:
    if not isinstance(value, kind):
        raise TypeError(f"Expected {kind.__name__}")




@dataclass(frozen=True)
class MouseEvent:
    type: MouseEventType
    x: int
    y: int
    button: MouseButton = MouseButton.NONE

    def __post_init__(self):
        _enum(self.type, MouseEventType)
        _enum(self.button, MouseButton)
        _integer(self.x, "x")
        _integer(self.y, "y")
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
            _integer(getattr(self, name), name)




class InputView:
    """Input methods shared by the public View, with no window-framework state."""

    def _input_call(self, name, *args):
        from .api import _call
        return _call(getattr(self._native, name), *args)

    def fire_mouse_event(self, event: MouseEvent) -> None:
        if not isinstance(event, MouseEvent):
            raise TypeError("event must be MouseEvent")
        self._input_call("fire_mouse_event", int(event.type), event.x, event.y, int(event.button))

    def fire_scroll_event(self, event: ScrollEvent) -> None:
        if not isinstance(event, ScrollEvent):
            raise TypeError("event must be ScrollEvent")
        self._input_call("fire_scroll_event", int(event.type), event.delta_x, event.delta_y, event.x, event.y)


    def focus(self) -> None:
        self._input_call("focus")

    def unfocus(self) -> None:
        self._input_call("unfocus")

    @property
    def has_focus(self) -> bool:
        from .api import _call
        return _call(lambda: self._native.has_focus)

    @property
    def has_input_focus(self) -> bool:
        from .api import _call
        return _call(lambda: self._native.has_input_focus)

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



