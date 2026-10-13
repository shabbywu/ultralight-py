"""Save a transparent HTML snapshot: python examples/images.py capture.png.

Requires pip install 'ultralight-py[pillow]'. Pixel conversion itself has no extras.
"""

import argparse
import time

from ultralight_py import Runtime
from ultralight_py.images import to_pillow


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", help="Output PNG path")
    args = parser.parse_args()
    with Runtime() as runtime, runtime.create_view(320, 180, transparent=True) as view:
        view.load_html(
            "<style>html,body{margin:0;background:transparent}"
            "div{width:200px;height:100px;background:rgba(255,0,0,.5)}</style><div></div>"
        )
        deadline = time.monotonic() + 5
        while not view.is_ready:
            if view.load_failure:
                raise RuntimeError(view.load_failure.description)
            if time.monotonic() >= deadline:
                raise TimeoutError("Page did not become ready")
            runtime.update()
            runtime.refresh_display()
            runtime.render()
            time.sleep(0.005)
        runtime.refresh_display()
        runtime.render()
        rgba = view.copy_pixels().to_rgba()
    # Independent image bytes remain usable after the Renderer has closed.
    to_pillow(rgba).save(args.output, format="PNG")
    print(rgba.width, rgba.height, rgba.format, args.output)


if __name__ == "__main__":
    main()
