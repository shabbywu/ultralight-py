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




@dataclass(frozen=True)
class MouseEvent:
    type: MouseEventType
    x: int
    y: int
    button: MouseButton = MouseButton.NONE

@dataclass(frozen=True)
class ScrollEvent:
    delta_x: int
    delta_y: int
    type: ScrollEventType = ScrollEventType.PIXEL
    x: int = -1
    y: int = -1


class InputView:

    def fire_mouse_event(self, event: MouseEvent) -> None:
        ...

    def fire_scroll_event(self, event: ScrollEvent) -> None:
        ...


    def focus(self) -> None:
        ...

    def unfocus(self) -> None:
        ...

    @property
    def has_focus(self) -> bool:
        ...

    @property
    def has_input_focus(self) -> bool:
        ...

    def mouse_move(self, x: int, y: int, *, button: MouseButton=MouseButton.NONE) -> None:
        ...

    def mouse_down(self, x: int, y: int, *, button: MouseButton=MouseButton.LEFT) -> None:
        ...

    def mouse_up(self, x: int, y: int, *, button: MouseButton=MouseButton.LEFT) -> None:
        ...

    def click(self, x: int, y: int, *, button: MouseButton=MouseButton.LEFT) -> None:
        ...

    def scroll(self, delta_x: int=0, delta_y: int=0, *, type: ScrollEventType=ScrollEventType.PIXEL, x: int=-1, y: int=-1) -> None:
        ...




