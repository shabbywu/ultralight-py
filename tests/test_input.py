import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "case",
    ["pointer", "keyboard", "guards", "close_view", "close_runtime", "resource_guard", "tk_window"],
)
def test_input_integration(case, tmp_path):
    if case == "tk_window":
        pytest.importorskip("tkinter")
        if sys.platform != "darwin" and sys.platform != "win32" and not os.environ.get("DISPLAY"):
            pytest.skip("Tk window verification requires a desktop")
    env = os.environ.copy()
    if env.get("PYTHONPATH"):
        env["PYTHONPATH"] = os.pathsep.join(
            str(Path(path).resolve()) for path in env["PYTHONPATH"].split(os.pathsep)
        )
    result = subprocess.run(
        [sys.executable, str(Path(__file__).with_name("input_cases.py")), case],
        check=False,
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
