"""Assemble a Flipper One MCU toolchain bundle for one platform.

    python3 -m assembler --platform darwin-arm64 --out dist

Fetches and verifies every component in manifest.json, lays out the bundle, writes the
env scripts and provenance, and packs a deterministic archive next to its .sha256.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from . import components, env, manifest, pack, provenance
from .fetch import Mirror, sha256_file
from .platforms import PLATFORMS, archive_name, host_platform

DEFAULT_CACHE = Path(os.environ.get('XDG_CACHE_HOME', Path.home() / '.cache')) / 'flipperone-mcu-toolchain'
TAG_RE = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}')


def _git(*args: str) -> str | None:
    try:
        return subprocess.run(['git', *args], cwd=manifest.REPO_ROOT, check=True, timeout=60,
                              capture_output=True, text=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def source_commit() -> str:
    commit = _git('rev-parse', 'HEAD')
    if commit is None:
        return 'unknown'
    if _git('status', '--porcelain', '--untracked-files=no'):
        commit += '-dirty'
    return commit


def source_date_epoch() -> int:
    if os.environ.get('SOURCE_DATE_EPOCH'):
        return int(os.environ['SOURCE_DATE_EPOCH'])
    stamp = _git('log', '-1', '--format=%ct')
    if stamp:
        return int(stamp)
    print('warning: no commit and no SOURCE_DATE_EPOCH; using the current time, so this '
          'archive is not reproducible', file=sys.stderr)
    return int(time.time())


def default_tag() -> str:
    short = _git('rev-parse', '--short=12', 'HEAD')
    return f'dev-{short}' if short else 'dev-local'


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as out:
        out.write(content)


def assemble(platform_name: str, out: Path, tag: str, cache: Path, offline: bool, keep_tree: bool,
             mirror: Mirror | None = None) -> Path:
    platform = PLATFORMS[platform_name]
    mf = manifest.load()
    if platform_name not in mf.platforms:
        raise SystemExit(f'{platform_name} is not a platform of this manifest')
    epoch = source_date_epoch()
    commit = source_commit()

    staging = out / f'.staging-{platform_name}'
    bundle = staging / 'bundle'
    components.rmtree(staging)
    bundle.mkdir(parents=True)

    started = time.monotonic()
    for c in mf.components:
        print(f'[{c.name}] {c.version}', flush=True)
        components.install(c, mf, platform, bundle, cache, offline, mirror)

    for rel, content in env.scripts(mf, platform, tag).items():
        write(bundle / rel, content)
        if rel.endswith('.sh'):
            (bundle / rel).chmod(0o755)
    shutil.copyfile(manifest.REPO_ROOT / 'THIRD_PARTY.md', bundle / 'THIRD_PARTY.md')
    (bundle / 'licenses').mkdir(exist_ok=True)
    shutil.copyfile(manifest.REPO_ROOT / 'LICENSE', bundle / 'licenses' / 'LICENSE')
    write(bundle / 'toolchain.json', provenance.toolchain_json(mf, platform, tag, commit, epoch))
    write(bundle / 'SHA256SUMS', provenance.sha256sums(bundle))

    archive = out / archive_name(tag, platform_name)
    print(f'[pack] {archive}', flush=True)
    pack.pack(bundle, archive, epoch)
    digest = sha256_file(archive)
    write(archive.with_name(archive.name + '.sha256'), f'{digest}  {archive.name}\n')
    if keep_tree:
        tree = out / f'flipperone-mcu-toolchain-{tag}-{platform_name}'
        components.rmtree(tree)
        os.replace(bundle, tree)
        print(f'[tree] {tree}')
    components.rmtree(staging)
    print(f'[done] {digest}  {archive.name} ({archive.stat().st_size >> 20} MiB, '
          f'{time.monotonic() - started:.0f}s)')
    return archive


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='python3 -m assembler', description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--platform', default=host_platform(), choices=sorted(PLATFORMS),
                        help='bundle platform (default: this host)')
    parser.add_argument('--out', type=Path, default=manifest.REPO_ROOT / 'dist', help='output directory')
    parser.add_argument('--tag', default=None, help='bundle tag (default: dev-<commit>)')
    parser.add_argument('--cache-dir', type=Path, default=DEFAULT_CACHE, help='download cache')
    parser.add_argument('--offline', action='store_true', help='use only the cache, never the network')
    parser.add_argument('--keep-tree', action='store_true', help='also leave the unpacked bundle in --out')
    parser.add_argument('--mirror', default=os.environ.get('FLIPPERONE_TOOLCHAIN_MIRROR') or None,
                        help='owner/repo@tag of a mirror release to use when upstream fails '
                             '(default: $FLIPPERONE_TOOLCHAIN_MIRROR; GITHUB_TOKEN authenticates)')
    args = parser.parse_args(argv)
    if args.platform is None:
        parser.error('this host is not a bundle platform; pass --platform')
    tag = args.tag or default_tag()
    if not TAG_RE.fullmatch(tag):
        parser.error(f'tag must match {TAG_RE.pattern}')
    if sys.version_info < (3, 12):  # noqa: UP036 - run as a module, nothing enforces requires-python
        parser.error('the assembler needs Python 3.12 or newer')
    try:
        mirror = Mirror.parse(args.mirror) if args.mirror else None
    except ValueError as error:
        parser.error(str(error))
    args.out.mkdir(parents=True, exist_ok=True)
    assemble(args.platform, args.out.resolve(), tag, args.cache_dir.resolve(), args.offline, args.keep_tree, mirror)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
