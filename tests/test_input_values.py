from dataclasses import FrozenInstanceError

import pytest

from ultralight_py import (
    KeyEvent,
    KeyEventType,
    Modifiers,
    MouseEvent,
    MouseEventType,
    ScrollEvent,
)


def test_events_are_owned_immutable_data():
    event = MouseEvent(MouseEventType.MOVE, -10, 10000)
    with pytest.raises(FrozenInstanceError):
        event.x = 2
    assert event.x == -10
    assert ScrollEvent(0, -1).x == -1
    assert KeyEvent(KeyEventType.CHAR, text="中文🐉").text == "中文🐉"


@pytest.mark.parametrize(
    "callback,error",
    [
        (lambda: MouseEvent(MouseEventType.MOVE, True, 0), TypeError),
        (lambda: MouseEvent(MouseEventType.MOVE, 1.5, 0), TypeError),
        (lambda: MouseEvent(MouseEventType.MOVE, 2**31, 0), OverflowError),
        (lambda: MouseEvent(MouseEventType.DOWN, 0, 0), ValueError),
        (lambda: MouseEvent(0, 0, 0), TypeError),
        (lambda: ScrollEvent(0, False), TypeError),
        (lambda: KeyEvent(KeyEventType.KEY_UP, virtual_key_code=True), TypeError),
        (lambda: KeyEvent(KeyEventType.CHAR, text=b"x"), TypeError),
        (lambda: KeyEvent(KeyEventType.CHAR, modifiers=Modifiers(16)), ValueError),
        (lambda: KeyEvent(KeyEventType.CHAR, is_auto_repeat=1), TypeError),
    ],
)
def test_invalid_events_fail_before_dispatch(callback, error):
    with pytest.raises(error):
        callback()
