import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("case", ["automatic", "manual", "http"])
def test_page_waits_with_real_renderer(case, tmp_path):
    result = subprocess.run(
        [sys.executable, str(Path(__file__).with_name("waiting_cases.py")), case],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=25,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
