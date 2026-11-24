"""Check (or fill in) manifest hashes against upstream metadata, without downloading archives.

    python3 -m assembler.pin           # report mismatches and blanks, exit 1 if any
    python3 -m assembler.pin --write   # fill blank sha256/commit fields from upstream

Sources: the sha256 digest GitHub records for each release asset, the `.sha` file xPack
publishes next to each archive (cross-checked against the digest), the PyPI JSON API for
wheels, and `git ls-remote` for git tags. The assembler still verifies every download.
Set GITHUB_TOKEN to avoid the anonymous API rate limit.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import urllib.parse
import urllib.request
from functools import cache

from .fetch import USER_AGENT
from .manifest import MANIFEST

GITHUB_ASSET = re.compile(r'https://github\.com/([^/]+)/([^/]+)/releases/download/([^/]+)/([^/]+)$')
PYPI_FILE = re.compile(r'https://files\.pythonhosted\.org/packages/.+/([^/]+\.whl)$')


def _get(url: str, accept: str = 'application/json') -> bytes:
    headers = {'User-Agent': USER_AGENT, 'Accept': accept}
    token = os.environ.get('GITHUB_TOKEN') or os.environ.get('GH_TOKEN')
    if token and url.startswith('https://api.github.com/'):
        headers['Authorization'] = f'Bearer {token}'
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as response:
        return response.read()


@cache
def _github_release(owner: str, repo: str, tag: str) -> dict[str, str]:
    data = json.loads(_get(f'https://api.github.com/repos/{owner}/{repo}/releases/tags/{tag}'))
    return {a['name']: (a.get('digest') or '').removeprefix('sha256:') for a in data['assets']}


@cache
def _pypi(name: str, version: str) -> dict[str, str]:
    data = json.loads(_get(f'https://pypi.org/pypi/{name}/{version}/json'))
    return {u['filename']: u['digests']['sha256'] for u in data['urls']}


def _hash_download(url: str) -> str:
    print(f'   (no upstream digest; hashing a download of {url})', flush=True)
    request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    with urllib.request.urlopen(request, timeout=300) as response:
        return hashlib.file_digest(response, 'sha256').hexdigest()


def upstream_sha256(url: str) -> str:
    if m := GITHUB_ASSET.match(url):
        owner, repo, tag, name = m.groups()
        name = urllib.parse.unquote(name)
        assets = _github_release(owner, repo, tag)
        if name not in assets:
            raise LookupError(f'{url}: not an asset of {owner}/{repo} {tag}')
        digest = assets[name]
        if owner == 'xpack-dev-tools':
            sidecar = _get(url + '.sha', accept='text/plain').decode().split()[0]
            if digest and sidecar != digest:
                raise LookupError(f'{url}: xPack .sha {sidecar} disagrees with GitHub {digest}')
            digest = sidecar
        return digest or _hash_download(url)
    if m := PYPI_FILE.match(url):
        filename = m.group(1)
        name, version = filename.split('-')[:2]
        digest = _pypi(name, version).get(filename)
        if not digest:
            raise LookupError(f'{url}: not in the PyPI release')
        return digest
    raise LookupError(f'{url}: no metadata source; hash it by hand')


def git_tag_commit(url: str, ref: str) -> str:
    out = subprocess.run(['git', 'ls-remote', url, f'refs/tags/{ref}', f'refs/tags/{ref}^{{}}'],
                         check=True, timeout=120, capture_output=True, text=True).stdout
    refs = dict(reversed(line.split('\t')) for line in out.splitlines())
    commit = refs.get(f'refs/tags/{ref}^{{}}') or refs.get(f'refs/tags/{ref}')
    if not commit:
        raise LookupError(f'{url}: no tag {ref}')
    return commit


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='python3 -m assembler.pin', description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--write', action='store_true', help='fill blank fields in manifest.json')
    args = parser.parse_args(argv)

    data = json.loads(MANIFEST.read_text())
    problems = 0
    for c in data['components']:
        if c['kind'] == 'archive':
            for key, spec in c['assets'].items():
                try:
                    digest = upstream_sha256(spec['url'])
                except LookupError as error:
                    print(f'?? {c["name"]}/{key}: {error}')
                    problems += 1
                    continue
                if not spec.get('sha256') and args.write:
                    spec['sha256'] = digest
                    print(f'++ {c["name"]}/{key}: {digest}')
                elif spec.get('sha256') != digest:
                    print(f'!! {c["name"]}/{key}: manifest {spec.get("sha256") or "(blank)"}, upstream {digest}')
                    problems += 1
                else:
                    print(f'ok {c["name"]}/{key}')
        elif c['kind'] == 'git':
            commit = git_tag_commit(c['url'], c['ref'])
            if not c.get('commit') and args.write:
                c['commit'] = commit
                print(f'++ {c["name"]}: {commit}')
            elif c.get('commit') != commit:
                print(f'!! {c["name"]}: manifest {c.get("commit") or "(blank)"}, tag {c["ref"]} is {commit}')
                problems += 1
            else:
                print(f'ok {c["name"]}')
    if args.write:
        MANIFEST.write_text(json.dumps(data, indent=2) + '\n')
    return 1 if problems else 0


if __name__ == '__main__':
    raise SystemExit(main())
