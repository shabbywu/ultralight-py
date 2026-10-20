import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "case",
    [
        "arrays",
        "dictionaries",
        "js_arrays",
        "js_objects",
        "identity",
        "snapshots",
        "lifecycle",
        "asynchronous",
    ],
)
def test_shared_containers(case, tmp_path):
    result = subprocess.run(
        [sys.executable, str(Path(__file__).with_name("container_cases.py")), case],
        check=False,
        cwd=tmp_path,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
