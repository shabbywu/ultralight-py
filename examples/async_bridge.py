"""Python hosts both schedulers; no rendering is required for this example."""

import asyncio
from ultralight_py import Runtime
from ultralight_py.integrations.asyncio import run

runtime = Runtime()
view = runtime.create_view(320, 200)
ready = False


def loaded(event):
    global ready
    if event.is_main_frame:
        ready = True


async def main():
    view.set_callbacks(dom_ready=loaded)
    view.load_html("<body>async bridge</body>")
    while not ready:
        await asyncio.sleep(0.01)

    async def double(value):
        await asyncio.sleep(0.05)
        return value * 2

    view.bind_function("double", double)
    print(await view.evaluate_async("double(21).then(x => ({answer: x}))"))


try:
    run(main(), runtime=runtime)
finally:
    runtime.close()
