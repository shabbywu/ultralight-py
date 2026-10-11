import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize('case', ['pointer', 'keyboard', 'guards', 'close_view', 'close_runtime',
                                  'resource_guard'])
def test_input_integration(case, tmp_path):
    env = os.environ.copy()
    if env.get('PYTHONPATH'):
        env['PYTHONPATH'] = os.pathsep.join(str(Path(path).resolve()) for path in env['PYTHONPATH'].split(os.pathsep))
    result = subprocess.run([sys.executable, str(Path(__file__).with_name('input_cases.py')), case],
                            cwd=tmp_path, env=env, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
