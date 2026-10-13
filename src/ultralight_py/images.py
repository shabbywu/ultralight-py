"""Independent RGBA images and optional Pillow/NumPy outputs."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from ultralight_py import _native

if TYPE_CHECKING:
    import numpy as np
    from numpy.typing import NDArray
    from PIL.Image import Image

    from ultralight_py.api import PixelBuffer


def _image_size(width: int, height: int) -> int:
    for name, value in (("width", width), ("height", height)):
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{name} must be an integer")
        if not 0 < value <= 0xFFFFFFFF:
            raise ValueError(f"{name} must be a positive uint32 value")
    size = width * height * 4
    if size > sys.maxsize:
        raise OverflowError("Image size exceeds the native buffer limit")
    return size


@dataclass(frozen=True)
class RGBAImage:
    """Owned, tightly packed RGBA8 pixels with straight (non-premultiplied) alpha."""

    width: int
    height: int
    data: bytes

    def __post_init__(self) -> None:
        if not isinstance(self.data, bytes):
            raise TypeError("data must be bytes")
        if len(self.data) != _image_size(self.width, self.height):
            raise ValueError("data length must equal width * height * 4")

    @property
    def row_bytes(self) -> int:
        return self.width * 4

    @property
    def format(self) -> Literal["RGBA8"]:
        return "RGBA8"


def to_rgba(frame: PixelBuffer | RGBAImage) -> RGBAImage:
    """Convert a BGRA snapshot, ignoring row padding and normalizing zero alpha."""
    from ultralight_py.api import PixelBuffer

    if isinstance(frame, RGBAImage):
        return frame
    if not isinstance(frame, PixelBuffer):
        raise TypeError("frame must be a PixelBuffer or RGBAImage")
    if frame.format != "BGRA8Premultiplied":
        raise ValueError("Unsupported pixel format; expected BGRA8Premultiplied")
    data = _native._bgra_to_rgba(frame.data, frame.width, frame.height, frame.row_bytes)
    return RGBAImage(frame.width, frame.height, data)


def to_pillow(frame: PixelBuffer | RGBAImage) -> Image:
    """Return an independent Pillow RGBA image; requires the pillow extra."""
    try:
        from PIL import Image
    except ModuleNotFoundError as error:
        if error.name != "PIL":
            raise
        raise ImportError("Install Pillow with pip install 'ultralight-py[pillow]'") from error
    rgba = to_rgba(frame)
    return Image.frombytes("RGBA", (rgba.width, rgba.height), rgba.data)


def to_numpy(frame: PixelBuffer | RGBAImage, *, copy: bool = True) -> NDArray[np.uint8]:
    """Return H×W×4 uint8 RGBA; copy=False shares converted bytes as a read-only view."""
    if not isinstance(copy, bool):
        raise TypeError("copy must be a bool")
    try:
        import numpy as np
    except ModuleNotFoundError as error:
        if error.name != "numpy":
            raise
        raise ImportError("Install NumPy with pip install 'ultralight-py[numpy]'") from error
    rgba = to_rgba(frame)
    array = np.frombuffer(rgba.data, dtype=np.uint8).reshape(rgba.height, rgba.width, 4)
    return array.copy(order="C") if copy else array
