import gc
import importlib.util
import io
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError

import pytest

from ultralight_py import PixelBuffer, RGBAImage, _native
from ultralight_py.images import to_numpy, to_pillow, to_rgba


def frame(data, *, width=1, height=1, stride=None, format="BGRA8Premultiplied"):
    return PixelBuffer(
        width, height, width * 4 if stride is None else stride, format, (0, 0, 0, 0), data
    )


def test_stride_channels_orientation_and_ownership():
    # Distinct rows and odd stride expose channel swaps, padding reads, and flipping.
    source = bytes([9, 17, 33, 255, 0, 0, 128, 128, 255, 255, 255, 0])
    source += b"padding" + bytes([4, 8, 12, 255]) * 3
    pixels = frame(source, width=3, height=2, stride=19)
    rgba = pixels.to_rgba()
    assert isinstance(rgba, RGBAImage)
    assert (rgba.width, rgba.height, rgba.row_bytes, rgba.format) == (3, 2, 12, "RGBA8")
    assert (
        rgba.data
        == bytes([33, 17, 9, 255, 255, 0, 0, 128, 0, 0, 0, 0]) + bytes([12, 8, 4, 255]) * 3
    )
    assert pixels.data == source
    assert to_rgba(rgba) is rgba
    assert to_rgba(pixels) == rgba
    assert pixels.to_rgba() is not rgba
    with pytest.raises(FrozenInstanceError):
        rgba.width = 8


def test_exhaustive_unpremultiplication():
    # Include invalid premultiplied values to verify saturation, not byte wrapping.
    raw = bytes(v for a in range(256) for c in range(256) for v in (c, 255 - c, c // 2, a))
    expected = bytearray()
    for a in range(256):
        for c in range(256):
            channels = (c // 2, 255 - c, c)
            expected.extend(min(255, value * 255 // a) if a else 0 for value in channels)
            expected.append(a)
    assert frame(raw, width=256, height=256).to_rgba().data == expected


@pytest.mark.parametrize("data", [b"\x01\x02\x03\xff", b"\x01\x02\x03\xffextra"])
def test_extra_bytes_and_single_row_stride(data):
    assert frame(data, stride=100).to_rgba().data == b"\x03\x02\x01\xff"


@pytest.mark.parametrize(
    ("kwargs", "error"),
    [
        ({"width": True}, TypeError),
        ({"height": 1.0}, TypeError),
        ({"width": 0}, ValueError),
        ({"height": -1}, ValueError),
        ({"width": 2**32}, ValueError),
        ({"stride": False}, TypeError),
        ({"stride": "4"}, TypeError),
        ({"stride": -4}, ValueError),
        ({"stride": 3}, ValueError),
        ({"stride": sys.maxsize + 1}, ValueError),
        ({"height": 2, "stride": sys.maxsize}, OverflowError),
        ({"width": 2**32 - 1, "height": 2**32 - 1}, OverflowError),
        ({"format": "RGBA8"}, ValueError),
    ],
)
def test_invalid_pixel_buffers(kwargs, error):
    with pytest.raises(error):
        frame(b"\0" * 4, **kwargs).to_rgba()


@pytest.mark.parametrize("data", [bytearray(4), memoryview(bytes(4)), "abcd", None])
def test_mutable_or_non_bytes_input(data):
    with pytest.raises(TypeError):
        frame(data).to_rgba()


def test_short_data_and_public_input_type():
    for pixels in (frame(bytes(3)), frame(bytes(19), width=2, height=2, stride=12)):
        with pytest.raises(ValueError, match="too short"):
            pixels.to_rgba()
    with pytest.raises(TypeError):
        to_rgba(object())
    # The private native entry also enforces its own boundary checks.
    with pytest.raises(TypeError):
        _native._bgra_to_rgba(bytes(4), True, 1, 4)


@pytest.mark.parametrize(
    ("width", "height", "data", "error"),
    [
        (0, 1, b"", ValueError),
        (1, True, bytes(4), TypeError),
        (1, 1, bytes(3), ValueError),
        (1, 1, bytes(5), ValueError),
        (1, 1, bytearray(4), TypeError),
        (2**32 - 1, 2**32 - 1, b"", OverflowError),
    ],
)
def test_rgba_image_validation(width, height, data, error):
    with pytest.raises(error):
        RGBAImage(width, height, data)


def test_concurrent_conversion():
    pixels = frame(bytes([8, 16, 32, 64]) * (320 * 240), width=320, height=240)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: pixels.to_rgba(), range(8)))
    assert all(image.data == bytes([127, 63, 31, 64]) * (320 * 240) for image in results)
    assert len({id(image.data) for image in results}) == 8


def test_pillow_ownership_and_png_roundtrip():
    Image = pytest.importorskip("PIL.Image")
    pixels = frame(bytes([0, 0, 128, 128]))
    rgba = pixels.to_rgba()
    image = to_pillow(pixels)
    assert image.mode == "RGBA" and image.size == (1, 1)
    assert image.tobytes() == rgba.data == to_pillow(rgba).tobytes()
    output = io.BytesIO()
    image.save(output, format="PNG")
    output.seek(0)
    assert Image.open(output).tobytes() == rgba.data
    image.putpixel((0, 0), (0, 0, 0, 0))
    assert rgba.data == bytes([255, 0, 0, 128])
    assert pixels.data == bytes([0, 0, 128, 128])


def test_numpy_ownership_and_pillow_consistency():
    np = pytest.importorskip("numpy")
    pixels = frame(bytes([9, 17, 33, 255, 0, 0, 128, 128]), width=2)
    rgba = pixels.to_rgba()
    array = to_numpy(pixels)
    assert array.shape == (1, 2, 4) and array.dtype == np.uint8
    assert array.flags.c_contiguous and array.flags.writeable and array.flags.owndata
    assert array.tobytes() == rgba.data
    if importlib.util.find_spec("PIL"):
        assert array.tobytes() == to_pillow(pixels).tobytes()
    array[:] = 0
    assert rgba.data == bytes([33, 17, 9, 255, 255, 0, 0, 128])
    readonly = to_numpy(rgba, copy=False)
    assert not readonly.flags.writeable and readonly.flags.c_contiguous
    assert np.shares_memory(readonly, np.frombuffer(rgba.data, dtype=np.uint8))
    expected_hex = rgba.data.hex()
    del pixels, rgba
    gc.collect()
    assert readonly.tobytes().hex() == expected_hex
    with pytest.raises(ValueError):
        readonly[:] = 0
    with pytest.raises(ValueError):
        readonly.setflags(write=True)
    with pytest.raises(TypeError):
        to_numpy(RGBAImage(1, 1, bytes(4)), copy=1)


def test_optional_dependencies_are_lazy_and_errors_are_actionable():
    code = """
import importlib.abc
import sys
class BlockOptional(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in ("PIL", "numpy"):
            raise ModuleNotFoundError("blocked optional dependency", name=fullname.split(".")[0])
sys.meta_path.insert(0, BlockOptional())
import ultralight_py
from ultralight_py.images import to_pillow, to_numpy
frame = ultralight_py.PixelBuffer(1, 1, 4, "BGRA8Premultiplied", (0,0,0,0), bytes([0,0,128,128]))
assert frame.to_rgba().data == bytes([255,0,0,128])
assert "PIL" not in sys.modules and "numpy" not in sys.modules
for function, extra in ((to_pillow, "pillow"), (to_numpy, "numpy")):
    try:
        function(frame)
    except ImportError as error:
        assert "ultralight-py[" + extra + "]" in str(error), str(error)
    else:
        raise AssertionError("Missing dependency was accepted")
"""
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=20, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_native_loop_releases_gil():
    # Disable timed Python thread switching in a child: the worker can advance
    # during the conversion only if the native operation actually releases GIL.
    code = """
import sys
import threading
from ultralight_py import PixelBuffer
ready, start, progressed = threading.Event(), threading.Event(), threading.Event()
def work():
    ready.set()
    start.wait()
    progressed.set()
thread = threading.Thread(target=work)
thread.start()
ready.wait()
frame = PixelBuffer(3840, 2160, 15360, "BGRA8Premultiplied", (0,0,0,0), bytes([8,16,32,64])*3840*2160)
previous = sys.getswitchinterval()
sys.setswitchinterval(60)
try:
    start.set()
    image = frame.to_rgba()
    assert progressed.is_set(), "Native conversion held the GIL"
finally:
    sys.setswitchinterval(previous)
    start.set()
    thread.join()
"""
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=20, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr
