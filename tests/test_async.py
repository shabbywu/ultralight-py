import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("case", ["main", "manual", "failure", "run_failure"])
def test_async_bridge(case, tmp_path):
    env = os.environ.copy()
    if env.get("PYTHONPATH"):
        env["PYTHONPATH"] = os.pathsep.join(
            str(Path(p).resolve()) for p in env["PYTHONPATH"].split(os.pathsep)
        )
    result = subprocess.run(
        [sys.executable, str(Path(__file__).with_name("async_cases.py")), case],
        check=False,
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
