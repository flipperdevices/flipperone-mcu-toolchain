import importlib.util
import os
import py_compile

import pytest

from assembler import components


def compiled(tmp_path, name, text):
    source = tmp_path / 'pkg' / f'{name}.py'
    source.parent.mkdir(exist_ok=True)
    source.write_text(text)
    os.utime(source, (1_790_000_000, 1_790_000_000))
    pyc = py_compile.compile(str(source), cfile=importlib.util.cache_from_source(str(source)),
                             invalidation_mode=py_compile.PycInvalidationMode.TIMESTAMP)
    os.utime(source, (1_704_067_200, 1_704_067_200))  # what python-build-standalone ships
    return source, pyc


def test_restamp_makes_sources_match_their_bytecode(tmp_path):
    source, _ = compiled(tmp_path, 'mod', 'x = 1\n')
    assert components.restamp_pyc_sources(tmp_path) == 1
    assert int(source.stat().st_mtime) == 1_790_000_000


def test_restamp_skips_sources_whose_size_changed(tmp_path):
    source, _ = compiled(tmp_path, 'mod', 'x = 1\n')
    source.write_text('x = 12345\n')
    os.utime(source, (1_704_067_200, 1_704_067_200))
    assert components.restamp_pyc_sources(tmp_path) == 0
    assert int(source.stat().st_mtime) == 1_704_067_200


def test_restamp_ignores_hash_based_bytecode(tmp_path):
    source = tmp_path / 'mod.py'
    source.write_text('x = 1\n')
    py_compile.compile(str(source), invalidation_mode=py_compile.PycInvalidationMode.CHECKED_HASH)
    assert components.restamp_pyc_sources(tmp_path) == 0


def test_copy_licenses_requires_every_pattern_to_match(tmp_path):
    (tmp_path / 'tree' / 'top').mkdir(parents=True)
    (tmp_path / 'tree' / 'top' / 'LICENSE.md').write_text('l')
    components.copy_licenses(tmp_path / 'tree', ['*/LICENSE.md'], tmp_path / 'out')
    assert (tmp_path / 'out' / 'top' / 'LICENSE.md').read_text() == 'l'
    with pytest.raises(components.InstallError):
        components.copy_licenses(tmp_path / 'tree', ['*/COPYING'], tmp_path / 'out')


def test_drop_console_scripts_removes_files_and_record_lines(tmp_path):
    root = tmp_path / 'python'
    site = root / 'lib' / 'python3.12' / 'site-packages'
    info = site / 'tool-1.0.dist-info'
    info.mkdir(parents=True)
    (root / 'bin').mkdir()
    script = root / 'bin' / 'tool-cli'
    script.write_text('#!/abs/staging/python3\n')
    (site / 'tool.py').write_text('')
    (info / 'RECORD').write_text('../../../bin/tool-cli,sha256=x,22\ntool.py,sha256=y,0\n')
    components.drop_console_scripts(root, {script})
    assert not script.exists()
    assert (info / 'RECORD').read_text() == 'tool.py,sha256=y,0\n'


def test_keep_only_retains_listed_files(tmp_path):
    root = tmp_path / 'btstack'
    for rel in ('LICENSE', 'src/bluetooth.h', 'src/hci.c', 'port/big/blob', 'platform/embedded/hal_flash_bank.h'):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(rel)
    components.keep_only(root, ['LICENSE', 'src/bluetooth.h', 'platform/embedded/hal_flash_bank.h'])
    files = sorted(p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file())
    assert files == ['LICENSE', 'platform/embedded/hal_flash_bank.h', 'src/bluetooth.h']
    with pytest.raises(components.InstallError):
        components.keep_only(root, ['src/hci.c'])
