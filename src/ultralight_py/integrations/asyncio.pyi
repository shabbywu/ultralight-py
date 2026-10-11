from collections.abc import Coroutine
from typing import Any, TypeVar

from typing_extensions import Self

from ultralight_py.api import Runtime

_T = TypeVar("_T")

class Driver:
    runtime: Runtime
    closed: bool
    def close(self) -> None: ...
    def __enter__(self) -> Self: ...
    def __exit__(self, *exc: object) -> None: ...

def install(runtime: Runtime, update_interval: float = ...) -> Driver: ...
def run(main: Coroutine[Any, Any, _T], *, runtime: Runtime, update_interval: float = ...) -> _T: ...
