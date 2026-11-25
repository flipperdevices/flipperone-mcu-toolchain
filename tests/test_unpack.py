import io
import stat
import tarfile
import zipfile

import pytest

from assembler import pack, unpack


def tar_with(path, entries):
    with tarfile.open(path, 'w:gz') as tar:
        for name, kind, payload in entries:
            info = tarfile.TarInfo(name)
            if kind == 'file':
                info.size = len(payload)
                tar.addfile(info, io.BytesIO(payload))
            elif kind == 'symlink':
                info.type = tarfile.SYMTYPE
                info.linkname = payload
                tar.addfile(info)
    return path


def zip_with(path, entries):
    with zipfile.ZipFile(path, 'w') as zf:
        for name, kind, payload in entries:
            info = zipfile.ZipInfo(name)
            if kind == 'symlink':
                info.create_system = 3
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
                zf.writestr(info, payload)
            else:
                zf.writestr(info, payload)
    return path


@pytest.mark.parametrize('entries', [
    [('../evil', 'file', b'x')],
    [('ok/link', 'symlink', '../../outside')],
    [('ok/link', 'symlink', '/etc/passwd')],
])
def test_tar_rejects_escapes(tmp_path, entries):
    archive = tar_with(tmp_path / 'a.tar.gz', entries)
    with pytest.raises(tarfile.FilterError):
        unpack.extract(archive, tmp_path / 'out')
    assert not (tmp_path / 'evil').exists()


@pytest.mark.parametrize('entries', [
    [('../evil', 'file', b'x')],
    [('/abs/evil', 'file', b'x')],
    [('C:/evil', 'file', b'x')],
    [('ok/link', 'symlink', '../../outside')],
    [('ok/link', 'symlink', '/etc/passwd')],
])
def test_zip_rejects_escapes(tmp_path, entries):
    archive = zip_with(tmp_path / 'a.zip', entries)
    with pytest.raises(unpack.UnsafeArchive):
        unpack.extract(archive, tmp_path / 'out')
    assert not (tmp_path / 'evil').exists()


def test_tar_absolute_member_stays_inside(tmp_path):
    archive = tar_with(tmp_path / 'a.tar.gz', [('/abs/evil', 'file', b'x')])
    unpack.extract(archive, tmp_path / 'out')
    assert (tmp_path / 'out' / 'abs' / 'evil').read_bytes() == b'x'


def test_round_trip_keeps_exec_bits_and_links(tmp_path):
    src = tmp_path / 'src'
    (src / 'bin').mkdir(parents=True)
    (src / 'bin' / 'tool').write_text('#!/bin/sh\n')
    (src / 'bin' / 'tool').chmod(0o755)
    (src / 'bin' / 'alias').symlink_to('tool')
    (src / 'data').write_text('d')
    pack.pack_tar_gz(src, tmp_path / 'b.tar.gz', 1_700_000_000)
    unpack.extract(tmp_path / 'b.tar.gz', tmp_path / 'out')
    assert (tmp_path / 'out' / 'bin' / 'tool').stat().st_mode & 0o111
    assert (tmp_path / 'out' / 'bin' / 'alias').is_symlink()
    assert not (tmp_path / 'out' / 'data').stat().st_mode & 0o111


def test_zip_exec_bit_survives(tmp_path):
    src = tmp_path / 'src'
    src.mkdir()
    (src / 'tool').write_text('x')
    (src / 'tool').chmod(0o755)
    pack.pack_zip(src, tmp_path / 'b.zip', 1_700_000_000)
    unpack.extract(tmp_path / 'b.zip', tmp_path / 'out')
    assert (tmp_path / 'out' / 'tool').stat().st_mode & 0o111


def test_refuses_non_empty_destination(tmp_path):
    archive = tar_with(tmp_path / 'a.tar.gz', [('f', 'file', b'x')])
    (tmp_path / 'out').mkdir()
    (tmp_path / 'out' / 'existing').write_text('')
    with pytest.raises(FileExistsError):
        unpack.extract(archive, tmp_path / 'out')


def test_select_root(tmp_path):
    single = tmp_path / 'single'
    (single / 'top' / 'bin').mkdir(parents=True)
    assert unpack.select_root(single, None) == single / 'top'
    assert unpack.select_root(single, '') == single
    assert unpack.select_root(single, 'top/bin') == single / 'top' / 'bin'
    flat = tmp_path / 'flat'
    (flat / 'scripts').mkdir(parents=True)
    (flat / 'openocd').write_text('')
    assert unpack.select_root(flat, None) == flat
    with pytest.raises(FileNotFoundError):
        unpack.select_root(flat, 'missing')
    with pytest.raises(unpack.UnsafeArchive):
        unpack.select_root(flat, '../flat')


@pytest.mark.parametrize('suffix', ['tar.gz', 'zip'])
def test_exclude_skips_matching_members(tmp_path, suffix):
    entries = [('scripts/target/rp2350.cfg', 'file', b'x'), ('scripts/target/?1879x?1?.cfg', 'file', b'y')]
    archive = (tar_with if suffix == 'tar.gz' else zip_with)(tmp_path / f'a.{suffix}', entries)
    unpack.extract(archive, tmp_path / 'out', exclude=('scripts/target/?1879x?1?.cfg',))
    assert [p.name for p in (tmp_path / 'out' / 'scripts' / 'target').iterdir()] == ['rp2350.cfg']


def deb_with(path, entries, data_name='data.tar.xz'):
    """A Debian package: an ar archive holding debian-binary, control and data tarballs."""
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode='w:xz' if data_name.endswith('.xz') else 'w') as tar:
        for name, payload in entries:
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            tar.addfile(info, io.BytesIO(payload))
    out = bytearray(b'!<arch>\n')
    for name, blob in (('debian-binary', b'2.0\n'), ('control.tar.xz', b'x'), (data_name, data.getvalue())):
        out += f'{name:<16}{0:<12}{0:<6}{0:<6}{644:<8}{len(blob):<10}`\n'.encode() + blob
        if len(blob) & 1:
            out += b'\n'
    path.write_bytes(bytes(out))
    return path


def test_extracts_the_data_of_a_debian_package(tmp_path):
    deb = deb_with(tmp_path / 'x.deb', [('./usr/lib/libx.so.1', b'elf'), ('./usr/share/doc/x/copyright', b'c')])
    unpack.extract(deb, tmp_path / 'out')
    assert (tmp_path / 'out' / 'usr' / 'lib' / 'libx.so.1').read_bytes() == b'elf'


@pytest.mark.parametrize('content', [b'not an ar archive', b'!<arch>\n'])
def test_rejects_a_debian_package_without_data(tmp_path, content):
    deb = tmp_path / 'x.deb'
    deb.write_bytes(content)
    with pytest.raises(unpack.UnsafeArchive):
        unpack.extract(deb, tmp_path / 'out')


def test_a_debian_package_cannot_write_outside(tmp_path):
    deb = deb_with(tmp_path / 'x.deb', [('../evil', b'x')])
    with pytest.raises(tarfile.FilterError):
        unpack.extract(deb, tmp_path / 'out')
