import os
import subprocess
import sys
from pathlib import Path


def run_case(case, tmp_path):
    env = os.environ.copy()
    if env.get("PYTHONPATH"):
        env["PYTHONPATH"] = os.pathsep.join(
            str(Path(path).resolve()) for path in env["PYTHONPATH"].split(os.pathsep)
        )
    result = subprocess.run(
        [sys.executable, str(Path(__file__).with_name("session_cases.py")), case],
        check=False,
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_session_lifecycle(tmp_path):
    run_case("lifecycle", tmp_path)


def test_session_storage_and_restart(tmp_path):
    run_case("write", tmp_path)
    run_case("read", tmp_path)
