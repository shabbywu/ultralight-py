"""Python bindings for Ultralight."""

from ultralight_py import _native, _waiting

ErrorCode = _native.ErrorCode
FrameEvent = _native.FrameEvent
JavaScriptError = _native.JavaScriptError
LoadFailure = _native.LoadFailure
PageLoadError = _waiting.PageLoadError
Resource = _native.Resource
UltralightError = _native.UltralightError
undefined = _native.undefined

from ultralight_py.api import (
    JSValue,
    PixelBuffer,
    Runtime,
    Session,
    View,
)
from ultralight_py.appcore import Application, Window
from ultralight_py.events import Subscription
from ultralight_py.images import RGBAImage
from ultralight_py.input import (
    KeyCode,
    KeyEvent,
    KeyEventType,
    Modifiers,
    MouseButton,
    MouseEvent,
    MouseEventType,
    ScrollEvent,
    ScrollEventType,
)
from ultralight_py.objects import PythonBinding
from ultralight_py.registry import API

__all__ = [
    "API",
    "Application",
    "ErrorCode",
    "FrameEvent",
    "JSValue",
    "JavaScriptError",
    "KeyCode",
    "KeyEvent",
    "KeyEventType",
    "LoadFailure",
    "Modifiers",
    "MouseButton",
    "MouseEvent",
    "MouseEventType",
    "PageLoadError",
    "PixelBuffer",
    "PythonBinding",
    "RGBAImage",
    "Resource",
    "Runtime",
    "ScrollEvent",
    "ScrollEventType",
    "Session",
    "Subscription",
    "UltralightError",
    "View",
    "Window",
    "undefined",
]
