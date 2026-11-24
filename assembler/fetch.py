"""Download upstream files into a content-addressed cache and verify their sha256.

If upstream fails (gone, changed or unreachable), a mirror can stand in: a GitHub release
whose assets are named `<sha256>-<file name>`, filled by `python3 -m assembler.mirror`.
Whatever the source, the content must match the pinned sha256.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from functools import cache
from pathlib import Path

USER_AGENT = 'flipperone-mcu-toolchain-assembler'
CHUNK = 1 << 20


class FetchError(RuntimeError):
    pass


@dataclass(frozen=True)
class Mirror:
    repo: str  # owner/name
    tag: str

    @classmethod
    def parse(cls, value: str) -> Mirror:
        repo, sep, tag = value.partition('@')
        if not sep or repo.count('/') != 1 or not tag:
            raise ValueError(f'mirror must be owner/repo@tag, not {value!r}')
        return cls(repo, tag)


def mirror_name(sha256: str, filename: str) -> str:
    return f'{sha256}-{filename}'


def github_token() -> str | None:
    return os.environ.get('GITHUB_TOKEN') or os.environ.get('GH_TOKEN')


def sha256_file(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


class _DropAuthOnRedirect(urllib.request.HTTPRedirectHandler):
    """GitHub sends asset downloads to a presigned storage URL, which rejects a second
    credential; urllib would forward the Authorization header there."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None and urllib.parse.urlsplit(newurl).netloc != urllib.parse.urlsplit(req.full_url).netloc:
            new.remove_header('Authorization')
        return new


_opener = urllib.request.build_opener(_DropAuthOnRedirect)


def _request(url: str, accept: str | None = None) -> urllib.request.Request:
    headers = {'User-Agent': USER_AGENT}
    if accept:
        headers['Accept'] = accept
    token = github_token()
    if token and url.startswith('https://api.github.com/'):
        headers['Authorization'] = f'Bearer {token}'
    return urllib.request.Request(url, headers=headers)


def _download(request: urllib.request.Request, target: Path, attempts: int = 4, timeout: float = 120) -> None:
    url = request.full_url
    for attempt in range(1, attempts + 1):
        try:
            with _opener.open(request, timeout=timeout) as response, target.open('wb') as out:
                shutil.copyfileobj(response, out, CHUNK)
            return
        except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
            if isinstance(error, urllib.error.HTTPError) and error.code in (401, 403, 404, 410):
                raise FetchError(f'{url}: HTTP {error.code}') from error
            if attempt == attempts:
                raise FetchError(f'{url}: {error}') from error
            delay = 2 ** attempt
            print(f'  retry {attempt}/{attempts - 1} in {delay}s: {error}', flush=True)
            time.sleep(delay)


@cache
def mirror_assets(mirror: Mirror) -> dict[str, str]:
    """Asset name -> API download URL for every asset of the mirror release."""
    assets: dict[str, str] = {}
    page = 1
    while True:
        url = f'https://api.github.com/repos/{mirror.repo}/releases/tags/{mirror.tag}'
        if page == 1:
            with _opener.open(_request(url, 'application/vnd.github+json'), timeout=60) as response:
                release_id = json.load(response)['id']
        listing = (f'https://api.github.com/repos/{mirror.repo}/releases/{release_id}/assets'
                   f'?per_page=100&page={page}')
        with _opener.open(_request(listing, 'application/vnd.github+json'), timeout=60) as response:
            batch = json.load(response)
        assets.update({a['name']: a['url'] for a in batch})
        if len(batch) < 100:
            return assets
        page += 1


def _download_verified(request: urllib.request.Request, sha256: str, partial: Path) -> None:
    _download(request, partial)
    actual = sha256_file(partial)
    if actual != sha256:
        partial.unlink()
        raise FetchError(f'{request.full_url}: sha256 mismatch\n  expected {sha256}\n  actual   {actual}')


def fetch(url: str, sha256: str, cache_dir: Path, offline: bool = False, mirror: Mirror | None = None) -> Path:
    """Path to a verified local copy of `url`, downloading it unless cached."""
    filename = urllib.parse.unquote(url.rsplit('/', 1)[-1])
    target = cache_dir / sha256 / filename
    if target.is_file():
        if sha256_file(target) == sha256:
            return target
        target.unlink()
    if offline:
        raise FetchError(f'offline and not cached: {url} (expected at {target})')
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + '.part')
    print(f'  download {url}', flush=True)
    try:
        _download_verified(_request(url), sha256, partial)
    except FetchError as upstream_error:
        if mirror is None:
            raise
        name = mirror_name(sha256, filename)
        print(f'  upstream failed ({upstream_error}); trying mirror {mirror.repo}@{mirror.tag}', flush=True)
        try:
            asset_url = mirror_assets(mirror).get(name)
        except (urllib.error.URLError, KeyError) as error:
            raise FetchError(f'{upstream_error}\n  mirror unavailable: {error}') from error
        if asset_url is None:
            raise FetchError(f'{upstream_error}\n  and the mirror has no {name}') from upstream_error
        _download_verified(_request(asset_url, 'application/octet-stream'), sha256, partial)
    os.replace(partial, target)
    return target
