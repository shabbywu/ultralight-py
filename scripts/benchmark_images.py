"""Measure synthetic pixel conversion and adapter costs, without creating a Renderer.

Run after installation: python scripts/benchmark_images.py --iterations 20
Optional adapters are measured when installed. Traced peak bytes cover allocations
visible to tracemalloc, not total RSS or all native allocations. Source bytes are
allocated before tracing. Results are local measurements, not frame-rate guarantees.
"""

import argparse
import importlib.util
import json
import math
import platform
import statistics
import sys
import time
import tracemalloc
from concurrent.futures import ThreadPoolExecutor
from functools import partial

from ultralight_py import PixelBuffer
from ultralight_py.images import to_numpy, to_pillow


def measure(operation, iterations):
    operation()
    timings = []
    for _ in range(iterations):
        start = time.perf_counter()
        result = operation()
        timings.append((time.perf_counter() - start) * 1000)
        del result
    tracemalloc.start()
    result = operation()
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    del result
    return {
        "p50_ms": round(statistics.median(timings), 3),
        "p95_ms": round(sorted(timings)[math.ceil(iterations * 0.95) - 1], 3),
        "peak_traced_bytes": peak,
    }


def pillow_conversion(pixels):
    from PIL import Image

    return Image.frombytes(
        "RGBa", (pixels.width, pixels.height), pixels.data, "raw", "BGRa", pixels.row_bytes
    ).convert("RGBA")


def converted_size(pixels):
    return len(pixels.to_rgba().data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=20)
    args = parser.parse_args()
    if args.iterations < 1:
        parser.error("--iterations must be positive")
    pillow = importlib.util.find_spec("PIL") is not None
    numpy = importlib.util.find_spec("numpy") is not None
    print(
        json.dumps(
            {
                "environment": {
                    "python": sys.version.split()[0],
                    "platform": platform.platform(),
                    "machine": platform.machine(),
                    "iterations": args.iterations,
                    "pillow": __import__("PIL").__version__ if pillow else None,
                    "numpy": __import__("numpy").__version__ if numpy else None,
                }
            }
        )
    )
    for width, height in ((1280, 720), (1920, 1080), (3840, 2160)):
        for alpha in (255, 128):
            # Include padding so benchmarks exercise the row-stride path.
            stride = width * 4 + 16
            data = (bytes([alpha // 4, alpha // 2, alpha, alpha]) * width + bytes(16)) * height
            pixels = PixelBuffer(
                width, height, stride, "BGRA8Premultiplied", (0, 0, width, height), data
            )
            rgba = pixels.to_rgba()
            operations = {"native_rgba": pixels.to_rgba}
            if pillow:
                operations["pillow_existing_path"] = partial(pillow_conversion, pixels)
                operations["pillow_from_bgra"] = partial(to_pillow, pixels)
                operations["pillow_from_rgba"] = partial(to_pillow, rgba)
            if numpy:
                operations["numpy_copy_from_bgra"] = partial(to_numpy, pixels)
                operations["numpy_copy_from_rgba"] = partial(to_numpy, rgba)
                operations["numpy_view_from_rgba"] = partial(to_numpy, rgba, copy=False)
            results = {
                name: measure(operation, args.iterations) for name, operation in operations.items()
            }
            with ThreadPoolExecutor(max_workers=2) as pool:
                start = time.perf_counter()
                list(pool.map(converted_size, [pixels] * (args.iterations * 2)))
                elapsed = time.perf_counter() - start
            print(
                json.dumps(
                    {
                        "width": width,
                        "height": height,
                        "alpha": alpha,
                        "operations": results,
                        "two_thread_frames_per_second": round(args.iterations * 2 / elapsed, 2),
                    }
                )
            )


if __name__ == "__main__":
    main()
