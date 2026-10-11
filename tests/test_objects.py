import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "case", ["instances", "containers", "conversion", "revocation", "cleanup", "guards"]
)
def test_object_bridge(case, tmp_path):
    env = os.environ.copy()
    if env.get("PYTHONPATH"):
        env["PYTHONPATH"] = os.pathsep.join(
            str(Path(path).resolve()) for path in env["PYTHONPATH"].split(os.pathsep)
        )
    result = subprocess.run(
        [sys.executable, str(Path(__file__).with_name("object_cases.py")), case],
        check=False,
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
