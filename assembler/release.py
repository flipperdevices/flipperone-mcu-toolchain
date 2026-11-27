"""Release metadata for a set of assembled bundles.

    python3 -m assembler.release --dist dist --tag v1 --image ghcr.io/o/r@sha256:... --out release

Writes, into --out:
- SHA256SUMS: one line per archive, in sha256sum format.
- release.json: the machine-readable interface for consumers. It lists each platform's
  archive (name, sha256, size), the Docker image (name, digest) and every component's
  version and license.
- release-notes.md: the same information for people.

The archives and their .sha256 files must already be in --dist, as the assembler writes them.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

from . import manifest
from .fetch import sha256_file
from .platforms import archive_name

RELEASE_TAG_RE = re.compile(r'v[1-9][0-9]*')
IMAGE_RE = re.compile(r'[a-z0-9.-]+(?:/[a-z0-9._-]+)+@sha256:[0-9a-f]{64}')


class ReleaseError(ValueError):
    pass


def collect_archives(dist: Path, tag: str, platforms: tuple[str, ...]) -> dict[str, dict]:
    """Every platform's archive, checked against the .sha256 the assembler wrote."""
    archives = {}
    for name in platforms:
        path = dist / archive_name(tag, name)
        if not path.is_file():
            raise ReleaseError(f'missing archive for {name}: {path.name}')
        digest = sha256_file(path)
        recorded = (dist / (path.name + '.sha256')).read_text().split()[0]
        if digest != recorded:
            raise ReleaseError(f'{path.name}: sha256 {digest} does not match its .sha256 ({recorded})')
        archives[name] = {'name': path.name, 'sha256': digest, 'size': path.stat().st_size}
    return archives


def release_record(mf: manifest.Manifest, tag: str, commit: str, archives: dict[str, dict],
                   image: str | None) -> dict:
    components = {}
    for c in mf.components:
        entry = {'version': c.version, 'license': c.license}
        if c.kind == 'git':
            entry['commit'] = c.raw['commit']
        elif c.kind in ('deb', 'files'):
            entry['platforms'] = sorted(c.raw['assets'])
        components[c.name] = entry
    record = {
        'schema': 1,
        'kind': 'flipperone-mcu-toolchain-release',
        'tag': tag,
        'source_commit': commit,
        'manifest_sha256': mf.sha256,
        'archives': archives,
        'image': None,
        'components': components,
    }
    if image:
        name, digest = image.split('@', 1)
        record['image'] = {'name': name, 'digest': digest}
    return record


def sha256sums(archives: dict[str, dict]) -> str:
    return ''.join(f'{a["sha256"]}  {a["name"]}\n' for a in archives.values())


def notes(record: dict) -> str:
    lines = [f'Flipper One MCU toolchain {record["tag"]}, from commit {record["source_commit"]}.', '']
    lines += ['| Platform | Archive | sha256 |', '|---|---|---|']
    lines += [f'| {p} | `{a["name"]}` | `{a["sha256"]}` |' for p, a in record['archives'].items()]
    if record['image']:
        image = record['image']
        lines += ['', 'Docker image (linux/amd64, linux/arm64):', '',
                  f'    {image["name"]}@{image["digest"]}']
    lines += ['', '| Component | Version | License |', '|---|---|---|']
    lines += [f'| {n} | {c["version"]}{" (" + ", ".join(c["platforms"]) + ")" if "platforms" in c else ""} '
              f'| {c["license"]} |' for n, c in record['components'].items()]
    lines += ['', '`release.json` holds the same data for tools; `SHA256SUMS` lists the archives.']
    return '\n'.join(lines) + '\n'


def _head_commit() -> str:
    return subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=manifest.REPO_ROOT, check=True, timeout=60,
                          capture_output=True, text=True).stdout.strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='python3 -m assembler.release', description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--dist', type=Path, required=True, help='directory with the assembled archives')
    parser.add_argument('--tag', required=True, help='release tag, v<N>')
    parser.add_argument('--image', help='pushed image as name@sha256:digest')
    parser.add_argument('--out', type=Path, required=True, help='directory for the release files')
    args = parser.parse_args(argv)
    if not RELEASE_TAG_RE.fullmatch(args.tag):
        parser.error('release tags are v<N>, N a positive integer')
    if args.image and not IMAGE_RE.fullmatch(args.image):
        parser.error('--image must be name@sha256:<digest>')

    mf = manifest.load()
    archives = collect_archives(args.dist, args.tag, mf.platforms)
    record = release_record(mf, args.tag, _head_commit(), archives, args.image)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / 'SHA256SUMS').write_text(sha256sums(archives))
    (args.out / 'release.json').write_text(json.dumps(record, indent=2) + '\n')
    (args.out / 'release-notes.md').write_text(notes(record))
    print((args.out / 'SHA256SUMS').read_text(), end='')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
