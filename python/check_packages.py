"""Check the bundled interpreter's packages; tests/smoke/run.py runs it with that interpreter.

- Every package in requirements.lock that applies here is installed at its locked version.
- Every package in requirements-build.in imports.
"""

from __future__ import annotations

import importlib
import re
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from pip._vendor.packaging.markers import Marker  # pip is always in the bundle: it installs the lock

HERE = Path(__file__).resolve().parent

# The module to import, where it is not the package name with '-' as '_'. Prefer one that
# loads the package's compiled parts.
IMPORTS = {
    'cryptography': 'cryptography.hazmat.primitives.hashes',
    'grpcio-tools': 'grpc_tools.protoc',
    'pillow': 'PIL.Image',
    'protobuf': 'google.protobuf',
    'pyserial': 'serial',
    'scons': 'SCons',
}

PIN = re.compile(r'([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s;\\#]+)\s*(?:;([^\\#]*))?')


def canonical(name: str) -> str:
    return re.sub(r'[-_.]+', '-', name).lower()


def pins(path: Path) -> dict[str, str]:
    """name -> version for every `name==version` line whose marker holds here."""
    out = {}
    for line in path.read_text(encoding='utf-8').splitlines():
        if (m := PIN.match(line)) and (not m[3] or Marker(m[3].strip()).evaluate()):
            out[canonical(m[1])] = m[2]
    return out


def main() -> int:
    locked = pins(HERE / 'requirements.lock')
    direct = pins(HERE / 'requirements-build.in')
    problems = []
    for name, want in sorted(locked.items()):
        try:
            have = version(name)
        except PackageNotFoundError:
            have = 'nothing'
        if have != want:
            problems.append(f'{name}: {have} installed, {want} locked')
    for name, want in sorted(direct.items()):
        if name not in locked:
            problems.append(f'{name}: in requirements-build.in, not in the lock')
        elif locked[name] != want:
            problems.append(f'{name}: requirements-build.in pins {want}, the lock {locked[name]}')
        module = IMPORTS.get(name, name.replace('-', '_'))
        try:
            importlib.import_module(module)
        except Exception as error:  # noqa: BLE001 - report every failing package, not the first
            problems.append(f'{name}: import {module}: {error!r}')
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        return 1
    print(f'python packages ok: {len(direct)} direct, {len(locked)} locked')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
