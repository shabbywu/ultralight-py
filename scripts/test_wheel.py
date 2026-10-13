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
