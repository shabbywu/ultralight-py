import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("case", ["main", "async"])
def test_registry(case, tmp_path):
    result = subprocess.run(
        [sys.executable, str(Path(__file__).with_name("registry_cases.py")), case],
        cwd=tmp_path,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
