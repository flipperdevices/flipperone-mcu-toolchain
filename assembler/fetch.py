"""Download upstream files into a content-addressed cache and verify their sha256."""

from __future__ import annotations

import hashlib
import os
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

USER_AGENT = 'flipperone-mcu-toolchain-assembler'
CHUNK = 1 << 20


class FetchError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _download(url: str, target: Path, attempts: int = 4, timeout: float = 120) -> None:
    request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response, target.open('wb') as out:
                shutil.copyfileobj(response, out, CHUNK)
            return
        except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
            if isinstance(error, urllib.error.HTTPError) and error.code in (403, 404, 410):
                raise FetchError(f'{url}: HTTP {error.code}') from error
            if attempt == attempts:
                raise FetchError(f'{url}: {error}') from error
            delay = 2 ** attempt
            print(f'  retry {attempt}/{attempts - 1} in {delay}s: {error}', flush=True)
            time.sleep(delay)


def fetch(url: str, sha256: str, cache_dir: Path, offline: bool = False) -> Path:
    """Path to a verified local copy of `url`, downloading it unless cached."""
    target = cache_dir / sha256 / urllib.parse.unquote(url.rsplit('/', 1)[-1])
    if target.is_file():
        if sha256_file(target) == sha256:
            return target
        target.unlink()
    if offline:
        raise FetchError(f'offline and not cached: {url} (expected at {target})')
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + '.part')
    print(f'  download {url}', flush=True)
    _download(url, partial)
    actual = sha256_file(partial)
    if actual != sha256:
        partial.unlink()
        raise FetchError(f'{url}: sha256 mismatch\n  expected {sha256}\n  actual   {actual}')
    os.replace(partial, target)
    return target
