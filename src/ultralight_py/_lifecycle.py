"""Process shutdown cleanup for native renderer resources."""

import atexit

from ultralight_py import _native

_registered = False


def shutdown() -> None:
    from ultralight_py.api.runtime import Runtime

    runtime = Runtime._instance
    if runtime is not None:
        runtime.close()
    _native._drain()


def register_shutdown() -> None:
    global _registered
    if _registered:
        return
    atexit.register(shutdown)
    _registered = True
