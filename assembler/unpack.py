"""Safe archive extraction: tar (gz/xz), zip/wheel and deb, never writing outside the target."""

from __future__ import annotations

import fnmatch
import io
import os
import posixpath
import stat
import tarfile
import zipfile
from pathlib import Path, PurePosixPath


class UnsafeArchive(ValueError):
    pass


def _check_member(name: str) -> PurePosixPath:
    if not name or name.startswith('/') or '\\' in name or (len(name) > 1 and name[1] == ':'):
        raise UnsafeArchive(f'unsafe member path: {name!r}')
    path = PurePosixPath(name)
    if '..' in path.parts:
        raise UnsafeArchive(f'unsafe member path: {name!r}')
    return path


def _excluded(name: str, exclude: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatchcase(name.rstrip('/'), pattern) for pattern in exclude)


def _extract_zip(archive: Path, dest: Path, exclude: tuple[str, ...]) -> None:
    with zipfile.ZipFile(archive) as zf:
        for info in zf.infolist():
            if _excluded(info.filename, exclude):
                continue
            rel = _check_member(info.filename.rstrip('/') or '.')
            target = dest.joinpath(*rel.parts)
            mode = info.external_attr >> 16
            if info.is_dir() or stat.S_ISDIR(mode):
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            if stat.S_ISLNK(mode):
                link = zf.read(info).decode()
                resolved = PurePosixPath(*rel.parts[:-1], link)
                if link.startswith('/') or '..' in PurePosixPath(posixpath.normpath(str(resolved))).parts:
                    raise UnsafeArchive(f'symlink escapes the archive: {info.filename} -> {link}')
                os.symlink(link, target)
                continue
            with zf.open(info) as src, target.open('wb') as out:
                while chunk := src.read(1 << 20):
                    out.write(chunk)
            if mode & 0o111:
                target.chmod(0o755)


def deb_data(archive: Path) -> bytes:
    """The data.tar.* member of a Debian package (an ar archive)."""
    data = archive.read_bytes()
    if data[:8] != b'!<arch>\n':
        raise UnsafeArchive(f'{archive.name}: not a Debian package')
    offset = 8
    while offset + 60 <= len(data):
        header = data[offset:offset + 60]
        name = header[:16].decode('ascii').strip().rstrip('/')
        size = int(header[48:58])
        offset += 60
        if name in ('data.tar.xz', 'data.tar.gz', 'data.tar'):
            return data[offset:offset + size]
        offset += size + (size & 1)
    raise UnsafeArchive(f'{archive.name}: no data.tar.xz, data.tar.gz or data.tar')


def extract(archive: Path, dest: Path, exclude: tuple[str, ...] = ()) -> None:
    """Unpack `archive` into the (new or empty) directory `dest`, skipping members whose
    archive path matches an `exclude` pattern (fnmatch)."""
    dest.mkdir(parents=True, exist_ok=True)
    if any(dest.iterdir()):
        raise FileExistsError(f'{dest} is not empty')
    name = archive.name
    if name.endswith(('.zip', '.whl')):
        _extract_zip(archive, dest, exclude)
    elif name.endswith(('.tar.gz', '.tgz', '.tar.xz', '.tar.bz2', '.tar', '.deb')):
        source = {'fileobj': io.BytesIO(deb_data(archive))} if name.endswith('.deb') else {'name': archive}
        with tarfile.open(**source) as tf:
            # The "data" filter rejects absolute paths, "..", links leaving dest and device files.
            members = [m for m in tf.getmembers() if not _excluded(m.name, exclude)]
            tf.extractall(dest, members=members, filter='data')
    else:
        raise ValueError(f'unsupported archive type: {name}')


def select_root(tree: Path, root: str | None) -> Path:
    """The directory inside an extracted archive to install.

    root None: the single top-level directory if there is exactly one entry and it is a
    directory, otherwise the archive root. root '': the archive root. Otherwise that path.
    """
    if root is None:
        entries = list(tree.iterdir())
        if len(entries) == 1 and entries[0].is_dir() and not entries[0].is_symlink():
            return entries[0]
        return tree
    if root == '':
        return tree
    selected = tree.joinpath(*_check_member(root).parts)
    if not selected.is_dir():
        raise FileNotFoundError(f'archive has no directory {root!r}')
    return selected
