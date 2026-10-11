import os
import subprocess
import sys
from pathlib import Path

import pytest

CASES = [
    "cache_path",
    "pixels",
    "transparent",
    "values",
    "handles",
    "callbacks",
    "errors",
    "lifecycle",
    "threading",
    "reentrant",
    "resources",
    "resource_errors",
    "http",
    "exit_cleanup",
]


@pytest.mark.parametrize("case", CASES)
def test_native_integration(case, tmp_path):
    # Absolute PYTHONPATH entries survive the isolated working directory, while
    # installed-wheel tests need no PYTHONPATH at all.
    env = os.environ.copy()
    if env.get("PYTHONPATH"):
        env["PYTHONPATH"] = os.pathsep.join(
            str(Path(path).resolve()) for path in env["PYTHONPATH"].split(os.pathsep)
        )
    result = subprocess.run(
        [sys.executable, str(Path(__file__).with_name("cases.py")), case],
        check=False,
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_cache_survives_process_restart(tmp_path):
    for case in ("cache_write", "cache_read"):
        test_native_integration(case, tmp_path)
