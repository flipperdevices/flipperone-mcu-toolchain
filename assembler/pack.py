"""Deterministic archives: the same tree and epoch always give the same bytes.

Entries are sorted, owners are 0/root, modes are normalised to 0755 (directories and
anything executable) or 0644, and the gzip header carries no name or time. Archives are
flat: the bundle root is the archive root.

Timestamps are clamped to SOURCE_DATE_EPOCH, not replaced: files unpacked from upstream
archives keep their (already deterministic) upstream times. That matters for Python: a
timestamp-validated .pyc records its source's exact mtime, and the interpreter rewrites it
on every start if the two disagree. Anything created during assembly is newer than the
epoch and gets the epoch.
"""

from __future__ import annotations

import gzip
import os
import stat
import struct
import tarfile
import time
import zipfile
from pathlib import Path

ZIP_MIN_EPOCH = 315532800  # 1980-01-01, the earliest time a zip entry can carry


def walk_sorted(root: Path) -> list[Path]:
    """Every entry under root (not root itself), sorted by POSIX relative path."""
    entries = []
    for dirpath, dirnames, filenames in os.walk(root):
        base = Path(dirpath)
        for name in dirnames + filenames:
            entries.append(base / name)
    return sorted(entries, key=lambda p: p.relative_to(root).as_posix())


def clamp(st_mtime: float, epoch: int) -> int:
    return min(int(st_mtime), epoch)


def _mode(st_mode: int) -> int:
    if stat.S_ISDIR(st_mode) or st_mode & 0o111:
        return 0o755
    return 0o644


def pack_tar_gz(root: Path, out: Path, epoch: int) -> None:
    with out.open('wb') as raw, \
            gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0, compresslevel=6) as gz, \
            tarfile.open(fileobj=gz, mode='w', format=tarfile.PAX_FORMAT) as tar:
        for path in walk_sorted(root):
            st = path.lstat()
            info = tarfile.TarInfo(path.relative_to(root).as_posix())
            info.mtime = clamp(st.st_mtime, epoch)
            info.uid = info.gid = 0
            info.uname = info.gname = ''
            if stat.S_ISLNK(st.st_mode):
                info.type = tarfile.SYMTYPE
                info.linkname = os.readlink(path)
                info.mode = 0o777
                tar.addfile(info)
            elif stat.S_ISDIR(st.st_mode):
                info.type = tarfile.DIRTYPE
                info.mode = 0o755
                tar.addfile(info)
            elif stat.S_ISREG(st.st_mode):
                info.size = st.st_size
                info.mode = _mode(st.st_mode)
                with path.open('rb') as stream:
                    tar.addfile(info, stream)
            else:
                raise ValueError(f'unsupported file type: {path}')


def _zip_info(name: str, mtime: int) -> zipfile.ZipInfo:
    """A zip entry whose time survives extraction: DOS time in UTC plus the exact UTC
    mtime in an extended-timestamp field, which Info-ZIP and Python honour."""
    info = zipfile.ZipInfo(name, time.gmtime(max(mtime, ZIP_MIN_EPOCH))[:6])
    info.create_system = 3
    info.extra = b'UT' + struct.pack('<HBl', 5, 1, max(mtime, ZIP_MIN_EPOCH))
    return info


def pack_zip(root: Path, out: Path, epoch: int) -> None:
    """Zip for Windows bundles. Symlinks to files are stored as the file they point to."""
    with zipfile.ZipFile(out, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for path in walk_sorted(root):
            rel = path.relative_to(root).as_posix()
            if path.is_symlink() and path.is_dir():
                raise ValueError(f'zip bundles cannot hold a directory symlink: {path}')
            st = path.stat()
            if path.is_dir():
                info = _zip_info(rel + '/', clamp(st.st_mtime, epoch))
                info.external_attr = (stat.S_IFDIR | 0o755) << 16 | 0x10
                zf.writestr(info, b'')
                continue
            info = _zip_info(rel, clamp(st.st_mtime, epoch))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (stat.S_IFREG | _mode(st.st_mode)) << 16
            with path.open('rb') as src, zf.open(info, 'w', force_zip64=True) as dst:
                while chunk := src.read(1 << 20):
                    dst.write(chunk)


def pack(root: Path, out: Path, epoch: int) -> None:
    if out.name.endswith('.zip'):
        pack_zip(root, out, epoch)
    elif out.name.endswith('.tar.gz'):
        pack_tar_gz(root, out, epoch)
    else:
        raise ValueError(f'unsupported archive type: {out.name}')
