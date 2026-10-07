"""Interpreter selection must preserve the user's actual virtual environment."""
import json
import os
from pathlib import Path
import subprocess
import sys
import venv


ROOT = Path(__file__).resolve().parents[1]


def test_explicit_symlinked_venv_preserves_environment_and_readonly_imports(tmp_path):
    selected = tmp_path / 'selected venv'
    venv.EnvBuilder(with_pip=False, symlinks=True).create(selected)
    executable = selected / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    module = tmp_path / 'probe_module.py'
    module.write_text('value = 42\n')
    env = {key: value for key, value in os.environ.items() if key in {'PATH', 'HOME', 'TMPDIR'}}
    env['N8N_EVOL_PYTHON'] = str(executable)
    probe = ('import json, sys, probe_module; '
             'print(json.dumps({"prefix": sys.prefix, "value": probe_module.value}))')
    result = subprocess.run([sys.executable, str(ROOT / 'helpers/python_runtime.py'), '-c', probe],
                            cwd=tmp_path, env=env, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    actual = json.loads(result.stdout)
    assert Path(actual['prefix']).resolve() == selected.resolve()
    assert actual['value'] == 42
    assert not (tmp_path / '__pycache__').exists()
