import io
import os
import tarfile
import zipfile

import pytest

from assembler import pack

EPOCH = 1_700_000_000
NEWER = EPOCH + 1000


def make_tree(root, mtime, umask_exec=False):
    (root / 'bin').mkdir(parents=True)
    (root / 'share' / 'doc').mkdir(parents=True)
    tool = root / 'bin' / 'tool'
    tool.write_text('#!/bin/sh\necho hi\n')
    tool.chmod(0o775 if umask_exec else 0o700)
    data = root / 'share' / 'doc' / 'README'
    data.write_text('readme\n')
    data.chmod(0o664 if umask_exec else 0o600)
    (root / 'b.txt').write_text('b')
    (root / 'a.txt').write_text('a')
    for path in root.rglob('*'):
        os.utime(path, (mtime, mtime), follow_symlinks=False)
    return root


@pytest.mark.parametrize('suffix', ['tar.gz', 'zip'])
def test_same_tree_gives_same_bytes(tmp_path, suffix):
    one = make_tree(tmp_path / 'one', NEWER)
    two = make_tree(tmp_path / 'two', NEWER + 5000, umask_exec=True)
    pack.pack(one, tmp_path / f'one.{suffix}', EPOCH)
    pack.pack(two, tmp_path / f'two.{suffix}', EPOCH)
    assert (tmp_path / f'one.{suffix}').read_bytes() == (tmp_path / f'two.{suffix}').read_bytes()


def test_older_mtimes_are_kept(tmp_path):
    root = make_tree(tmp_path / 'tree', 1_600_000_000)
    pack.pack_tar_gz(root, tmp_path / 'out.tar.gz', EPOCH)
    pack.pack_zip(root, tmp_path / 'out.zip', EPOCH)
    with tarfile.open(tmp_path / 'out.tar.gz') as tar:
        assert {m.mtime for m in tar.getmembers() if not m.issym()} == {1_600_000_000}
    with zipfile.ZipFile(tmp_path / 'out.zip') as zf:
        info = zf.getinfo('a.txt')
        assert info.date_time == (2020, 9, 13, 12, 26, 40)
        assert info.extra[4:] == b'\x01' + (1_600_000_000).to_bytes(4, 'little')


def test_tar_metadata_is_normalised(tmp_path):
    root = make_tree(tmp_path / 'tree', NEWER)
    (root / 'bin' / 'alias').symlink_to('tool')
    out = tmp_path / 'out.tar.gz'
    pack.pack_tar_gz(root, out, EPOCH)
    assert out.read_bytes()[4:8] == b'\0\0\0\0', 'gzip header mtime must be zero'
    with tarfile.open(out) as tar:
        members = tar.getmembers()
    names = [m.name for m in members]
    assert names == sorted(names)
    by_name = {m.name: m for m in members}
    assert all(m.mtime == EPOCH and m.uid == 0 and m.gid == 0 and not m.uname for m in members)
    assert by_name['bin/tool'].mode == 0o755
    assert by_name['share/doc/README'].mode == 0o644
    assert by_name['bin'].mode == 0o755
    assert by_name['bin/alias'].issym() and by_name['bin/alias'].linkname == 'tool'


def test_zip_metadata_is_normalised(tmp_path):
    root = make_tree(tmp_path / 'tree', NEWER)
    out = tmp_path / 'out.zip'
    pack.pack_zip(root, out, EPOCH)
    with zipfile.ZipFile(out) as zf:
        infos = zf.infolist()
        assert [i.filename for i in infos] == sorted(i.filename for i in infos)
        modes = {i.filename: i.external_attr >> 16 & 0o777 for i in infos}
        assert modes['bin/tool'] == 0o755
        assert modes['share/doc/README'] == 0o644
        assert {i.date_time for i in infos} == {(2023, 11, 14, 22, 13, 20)}
        assert zf.read('a.txt') == b'a'


def test_zip_clamps_pre_1980_epochs(tmp_path):
    root = make_tree(tmp_path / 'tree', 1_000_000)
    out = tmp_path / 'out.zip'
    pack.pack_zip(root, out, 0)
    with zipfile.ZipFile(io.BytesIO(out.read_bytes())) as zf:
        assert zf.infolist()[0].date_time == (1980, 1, 1, 0, 0, 0)


def test_unknown_archive_type(tmp_path):
    with pytest.raises(ValueError):
        pack.pack(tmp_path, tmp_path / 'x.rar', EPOCH)
