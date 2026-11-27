"""Copy every pinned upstream archive into a mirror release, so bundles stay buildable if
upstream deletes or replaces a file.

    python3 -m assembler.mirror --mirror owner/repo@mirror [--cache-dir DIR]

Each asset is stored as `<sha256>-<file name>`, verified against the manifest before
upload. Assets already present are skipped, and none are ever deleted, since older
toolchain tags may still need them. Uploads go through the `gh` CLI (GH_TOKEN needs
contents: write); the release is created as a prerelease on first use.

Archive, deb and files components and the patchelf wheels are mirrored: the Pico SDK comes from
git at pinned commits, and the Python packages from PyPI, which does not allow a release
file to be replaced.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import manifest
from .fetch import Mirror, fetch, mirror_assets, mirror_name

NOTES = ('Upstream archives pinned in manifest.json, kept in case upstream removes or replaces '
         'them. Each asset is named <sha256>-<file name>. Maintained by the Upstream workflow; '
         'do not edit by hand.')


def wanted(mf: manifest.Manifest) -> dict[str, tuple[str, str]]:
    """Mirror asset name -> (upstream URL, sha256), for every archive, deb, files and patchelf asset."""
    assets = [a for c in mf.components if c.kind in ('archive', 'deb', 'files') for a in c.all_assets()]
    assets += [mf.patchelf_asset(host) for host in mf.patchelf.get('assets', {})]
    return {mirror_name(a.sha256, a.filename): (a.url, a.sha256) for a in assets}


def gh(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(['gh', *args], check=False, timeout=1800, capture_output=True, text=True)


def ensure_release(mirror: Mirror, target: str) -> None:
    if gh('release', 'view', mirror.tag, '-R', mirror.repo).returncode == 0:
        return
    created = gh('release', 'create', mirror.tag, '-R', mirror.repo, '--prerelease', '--target', target,
                 '--title', 'Upstream mirror', '--notes', NOTES)
    if created.returncode != 0:
        raise SystemExit(f'cannot create release {mirror.tag}: {created.stderr.strip()}')


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='python3 -m assembler.mirror', description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--mirror', required=True, help='owner/repo@tag of the mirror release')
    parser.add_argument('--target', default='dev', help='branch the mirror tag is created on, if new')
    parser.add_argument('--cache-dir', type=Path, help='download cache (default: a temporary directory)')
    args = parser.parse_args(argv)
    mirror = Mirror.parse(args.mirror)

    ensure_release(mirror, args.target)
    present = set(mirror_assets(mirror))
    todo = {name: spec for name, spec in wanted(manifest.load()).items() if name not in present}
    print(f'{len(present)} assets in {mirror.repo}@{mirror.tag}; {len(todo)} to upload', flush=True)
    with tempfile.TemporaryDirectory(prefix='fo-mirror-') as tmp:
        cache = args.cache_dir or Path(tmp) / 'cache'
        for name, (url, sha256) in sorted(todo.items()):
            source = fetch(url, sha256, cache)
            staged = Path(tmp) / name
            shutil.copyfile(source, staged)
            uploaded = gh('release', 'upload', mirror.tag, str(staged), '-R', mirror.repo)
            staged.unlink()
            if args.cache_dir is None:
                source.unlink()
            if uploaded.returncode != 0:
                raise SystemExit(f'upload of {name} failed: {uploaded.stderr.strip()}')
            print(f'  uploaded {name}', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
