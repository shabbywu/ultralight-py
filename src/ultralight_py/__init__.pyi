from typing import ClassVar

class ErrorCode:
    InvalidArgument: ClassVar[ErrorCode]
    WrongThread: ClassVar[ErrorCode]
    Closed: ClassVar[ErrorCode]
    Busy: ClassVar[ErrorCode]
    PageGone: ClassVar[ErrorCode]
    CrossContext: ClassVar[ErrorCode]
    ScriptException: ClassVar[ErrorCode]
    HostException: ClassVar[ErrorCode]
    Unsupported: ClassVar[ErrorCode]
    TypeMismatch: ClassVar[ErrorCode]
    TraversalLimit: ClassVar[ErrorCode]
    __members__: ClassVar[dict[str, ErrorCode]]
    def __init__(self, value: int) -> None: ...
    @property
    def name(self) -> str: ...
    @property
    def value(self) -> int: ...
    def __int__(self) -> int: ...

class UltralightError(RuntimeError):
    code: ErrorCode
    stack: str
    source_url: str
    line: float
    column: float

class JavaScriptError(UltralightError): ...
class _Undefined: ...

undefined: _Undefined

class Resource:
    def __init__(
        self, data: bytes, mime_type: str | None = None, charset: str = "utf-8"
    ) -> None: ...
    @property
    def data(self) -> bytes: ...
    @property
    def mime_type(self) -> str: ...
    @property
    def charset(self) -> str: ...

class FrameEvent:
    @property
    def frame_id(self) -> int: ...
    @property
    def is_main_frame(self) -> bool: ...
    @property
    def url(self) -> str: ...

class LoadFailure:
    @property
    def frame(self) -> FrameEvent: ...
    @property
    def description(self) -> str: ...
    @property
    def domain(self) -> str: ...
    @property
    def code(self) -> int: ...

class PageLoadError(RuntimeError):
    failure: LoadFailure
    def __init__(self, failure: LoadFailure) -> None: ...

from ultralight_py.api import (
    JSArray as JSArray,
)
from ultralight_py.api import (
    JSObject as JSObject,
)
from ultralight_py.api import (
    JSValue as JSValue,
)
from ultralight_py.api import (
    PixelBuffer as PixelBuffer,
)
from ultralight_py.api import (
    Runtime as Runtime,
)
from ultralight_py.api import (
    Session as Session,
)
from ultralight_py.api import (
    View as View,
)
from ultralight_py.appcore import Application as Application
from ultralight_py.appcore import Window as Window
from ultralight_py.events import Subscription as Subscription
from ultralight_py.images import RGBAImage as RGBAImage
from ultralight_py.input import (
    KeyCode as KeyCode,
)
from ultralight_py.input import (
    KeyEvent as KeyEvent,
)
from ultralight_py.input import (
    KeyEventType as KeyEventType,
)
from ultralight_py.input import (
    Modifiers as Modifiers,
)
from ultralight_py.input import (
    MouseButton as MouseButton,
)
from ultralight_py.input import (
    MouseEvent as MouseEvent,
)
from ultralight_py.input import (
    MouseEventType as MouseEventType,
)
from ultralight_py.input import (
    ScrollEvent as ScrollEvent,
)
from ultralight_py.input import (
    ScrollEventType as ScrollEventType,
)
from ultralight_py.objects import PythonBinding as PythonBinding
from ultralight_py.registry import API as API
