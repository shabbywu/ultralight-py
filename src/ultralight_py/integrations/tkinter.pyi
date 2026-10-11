import tkinter as tk
from typing import Callable
from ultralight_py.api import View

class TkInputAdapter:
    def __init__(self, widget: tk.Misc, view: View, *,
                 coordinate_transform: Callable[[int, int], tuple[int, int]] | None = None,
                 wheel_pixels: int = 40) -> None: ...
    def close(self) -> None: ...
