#!/usr/bin/env python3
"""Run helpers with their dependencies; provision a private cached venv if needed."""
import hashlib
import importlib.metadata
import os
from pathlib import Path
import re
import subprocess
import sys
import venv


ROOT = Path(__file__).resolve().parent.parent


def dependencies_available(requirements: str) -> bool:
    for line in requirements.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        match = re.fullmatch(r'([A-Za-z0-9_-]+)>=(\d+(?:\.\d+)*)', line)
        if not match:
            return False
        try:
            installed = importlib.metadata.version(match[1])
        except importlib.metadata.PackageNotFoundError:
            return False
        version = re.match(r'\d+(?:\.\d+)*', installed)
        if version is None:
            return False
        actual = tuple(int(part) for part in version[0].split('.'))
        minimum = tuple(int(part) for part in match[2].split('.'))
        length = max(len(actual), len(minimum))
        if actual + (0,) * (length - len(actual)) < minimum + (0,) * (length - len(minimum)):
            return False
    return True


def runtime_python() -> Path:
    override = os.environ.get('N8N_EVOL_PYTHON')
    if override:
        # A virtualenv's interpreter is commonly a symlink. Preserve that path:
        # resolving its leaf would silently execute the base Python instead.
        chosen = Path(os.path.abspath(Path(override).expanduser()))
        if not chosen.is_file():
            raise ValueError('N8N_EVOL_PYTHON must point to an existing Python interpreter')
        return chosen
    if sys.version_info < (3, 11):
        raise ValueError('n8n-evol-I requires Python 3.11 or newer')
    requirements_file = ROOT / 'requirements.txt'
    requirements = requirements_file.read_text()
    if dependencies_available(requirements):
        return Path(sys.executable)
    base = Path(os.environ.get('N8N_EVOL_CACHE_HOME') or
                Path(os.environ.get('XDG_CACHE_HOME', Path.home() / '.cache')) / 'n8n-evol-I').expanduser().resolve()
    fingerprint = hashlib.sha256((requirements + sys.executable + sys.version).encode()).hexdigest()[:20]
    directory = base / 'python' / fingerprint
    if directory.is_symlink() or directory.resolve() != directory:
        raise ValueError('Python runtime cache must not redirect through symlinks')
    directory.mkdir(parents=True, exist_ok=True)
    python = directory / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    ready = directory / '.ready'
    # Concurrent hooks may request the same environment. Serialize creation;
    # normal cached launches avoid the installation path entirely.
    with (directory / '.install.lock').open('a') as lock:
        if os.name != 'nt':
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_EX)
        if not ready.is_file() or not python.is_file():
            print('Preparing n8n-evol-I Python dependencies in the tool cache...', file=sys.stderr)
            venv.EnvBuilder(with_pip=True).create(directory)
            subprocess.run([str(python), '-m', 'pip', 'install', '--quiet', '--disable-pip-version-check',
                            '-r', str(requirements_file)], check=True, stdout=sys.stderr)
            ready.write_text(fingerprint + '\n')
    return python


def main() -> None:
    # Installed plugins can be read-only. Keep helper imports from creating
    # bytecode beside the distributed source.
    os.environ.setdefault('PYTHONDONTWRITEBYTECODE', '1')
    try:
        python = runtime_python()
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        raise SystemExit(f'Python setup failed: {error}')
    if sys.argv[1:] == ['--prepare']:
        print(python)
        return
    os.execv(str(python), [str(python), *sys.argv[1:]])


if __name__ == '__main__':
    main()
