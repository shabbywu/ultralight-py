"""Run only the installed wheel in cibuildwheel's isolated test directory."""

import os
import subprocess
import sys
from pathlib import Path


def main():
    env = os.environ.copy()
    for key in list(env):
        if key.startswith(("ULTRALIGHT", "ULBIND17", "DYLD_")) or key in {
            "PYTHONPATH",
            "PYTHONHOME",
            "LD_LIBRARY_PATH",
            "LD_PRELOAD",
        }:
            del env[key]
    # Child tests must also avoid user site packages and source PYTHONPATH.
    env["PYTHONNOUSERSITE"] = "1"
    directory = Path(__file__).resolve().parents[1]
    probe = """
from pathlib import Path
import sys
import ultralight_py
package = Path(ultralight_py.__file__).resolve().parent
assert package.is_relative_to(Path(sys.prefix).resolve()), package
assert (package / 'py.typed').is_file()
assert (package / '__init__.pyi').is_file()
assert (package / 'images.pyi').is_file()
assert (package / 'appcore/__init__.pyi').is_file()
assert (package / 'api/__init__.pyi').is_file()
assert (package / 'registry.pyi').is_file()
from ultralight_py import API, Application, Window, Runtime, Session, View, JSArray, JSObject, JSValue, PixelBuffer
from ultralight_py.api.runtime import Runtime as ModuleRuntime, Session as ModuleSession
from ultralight_py.api.view import View as ModuleView
from ultralight_py.api.values import JSArray as ModuleJSArray, JSObject as ModuleJSObject, JSValue as ModuleJSValue, PixelBuffer as ModulePixelBuffer
from ultralight_py.appcore.application import Application as ModuleApplication
from ultralight_py.appcore.window import Window as ModuleWindow
assert (Runtime, Session, View, JSValue, PixelBuffer, Application, Window) == (
    ModuleRuntime, ModuleSession, ModuleView, ModuleJSValue, ModulePixelBuffer,
    ModuleApplication, ModuleWindow,
)
assert (JSArray, JSObject) == (ModuleJSArray, ModuleJSObject)
print('Installed wheel:', package)
"""
    subprocess.run([sys.executable, "-I", "-c", probe], cwd=directory, env=env, check=True)
    subprocess.run(
        [sys.executable, "-I", "-m", "pytest", "tests", "-q", "--import-mode=importlib"],
        cwd=directory,
        env=env,
        check=True,
    )


if __name__ == "__main__":
    main()
