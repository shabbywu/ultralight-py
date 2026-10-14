import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.skipif(
    sys.platform != "darwin", reason="Native AppCore desktop acceptance targets macOS"
)
@pytest.mark.parametrize(
    "case",
    [
        "cpu",
        "gpu",
        "sync",
        "runtime",
        "session",
        "view",
        "cancel",
        "window",
        "failure",
        "reentrant",
    ],
)
def test_appcore(case, tmp_path):
    result = subprocess.run(
        [sys.executable, str(Path(__file__).with_name("appcore_cases.py")), case],
        cwd=tmp_path,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
