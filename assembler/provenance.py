"""The bundle's toolchain.json and SHA256SUMS."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .fetch import sha256_file
from .manifest import REPO_ROOT, Manifest
from .pack import walk_sorted
from .platforms import Platform


def toolchain_json(manifest: Manifest, platform: Platform, tag: str, source_commit: str, epoch: int) -> str:
    components: dict[str, dict] = {}
    lock_sha256 = None
    for c in manifest.components:
        if not c.applies_to(platform):
            continue
        entry: dict = {'version': c.version, 'license': c.license}
        if c.kind in ('archive', 'deb'):
            asset = c.asset(platform)
            entry.update(url=asset.url, sha256=asset.sha256)
        elif c.kind == 'git':
            entry.update(url=c.raw['url'], commit=c.raw['commit'], submodules=c.raw.get('submodules', {}))
        elif c.kind == 'pip':
            lock = REPO_ROOT / c.raw['requirements']
            lock_sha256 = hashlib.sha256(lock.read_bytes()).hexdigest()
            entry.update(requirements=c.raw['requirements'], sha256=lock_sha256)
        components[c.name] = entry
    record = {
        'schema': 1,
        'kind': 'flipperone-mcu-toolchain',
        'tag': tag,
        'platform': platform.name,
        'source_commit': source_commit,
        'source_date_epoch': epoch,
        'manifest_sha256': manifest.sha256,
        'python_lock_sha256': lock_sha256,
        'components': components,
    }
    return json.dumps(record, indent=2) + '\n'


def sha256sums(bundle: Path) -> str:
    """sha256sum-compatible listing of every regular file except SHA256SUMS itself."""
    lines = []
    for path in walk_sorted(bundle):
        rel = path.relative_to(bundle).as_posix()
        if rel == 'SHA256SUMS' or path.is_symlink() or not path.is_file():
            continue
        lines.append(f'{sha256_file(path)}  {rel}\n')
    return ''.join(lines)
