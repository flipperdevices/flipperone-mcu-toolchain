import importlib.util
import os
import py_compile

import pytest

from assembler import components, manifest
from assembler.platforms import PLATFORMS
from tests.test_unpack import deb_with


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


@pytest.fixture
def fake_tools(monkeypatch):
    """Package downloads served from local files; runpath changes recorded, not made."""
    served, runpaths = {}, []
    monkeypatch.setattr(components, 'fetch', lambda url, sha256, *_a, **_k: served[url])
    monkeypatch.setattr(components, 'patchelf', lambda *_a, **_k: 'patchelf')
    monkeypatch.setattr(components, 'set_runpath',
                        lambda _tool, binary, runpath: runpaths.append((binary.name, runpath)))
    return served, runpaths


def test_install_deb_copies_the_listed_libraries(tmp_path, fake_tools):
    served, runpaths = fake_tools
    mf = manifest.load()
    c = mf.component('libusb')
    platform = PLATFORMS['linux-x86_64']
    asset = c.asset(platform)
    (name, member), = asset.files
    served[asset.url] = deb_with(tmp_path / 'p.deb', [(member, b'elf'), (c.license_files[0], b'LGPL')])
    bundle = tmp_path / 'bundle'
    bundle.mkdir()
    components.install(c, mf, platform, bundle, tmp_path / 'cache', offline=True)
    assert (bundle / c.dest / name).read_bytes() == b'elf'
    assert (bundle / 'licenses' / 'libusb' / c.license_files[0]).read_text() == 'LGPL'
    assert runpaths == [(name, '$ORIGIN')]
    with pytest.raises(components.InstallError, match='already exists'):
        components.install(c, mf, platform, bundle, tmp_path / 'cache', offline=True)


def test_deb_components_are_skipped_off_linux(tmp_path, fake_tools):
    mf = manifest.load()
    components.install(mf.component('libusb'), mf, PLATFORMS['darwin-arm64'], tmp_path, tmp_path, offline=True)
    assert list(tmp_path.iterdir()) == []


def test_install_files_puts_the_runtime_next_to_each_tool(tmp_path, fake_tools):
    import zipfile
    served, _ = fake_tools
    mf = manifest.load()
    c = mf.component('msvc-runtime-arm64')
    platform = PLATFORMS['windows-arm64']
    asset = c.asset(platform)
    wheel = tmp_path / 'rt.whl'
    with zipfile.ZipFile(wheel, 'w') as zf:
        for member in sorted({member for _, member in asset.files}):
            zf.writestr(member, member.rsplit('/', 1)[-1])
        zf.writestr(c.license_files[0], 'license')
    served[asset.url] = wheel
    bundle = tmp_path / 'bundle'
    for target, _ in asset.files:
        (bundle / target).parent.mkdir(parents=True, exist_ok=True)
    components.install(c, mf, platform, bundle, tmp_path / 'cache', offline=True)
    for target, member in asset.files:
        assert (bundle / target).read_text() == member.rsplit('/', 1)[-1]
    assert (bundle / 'licenses' / c.name / c.license_files[0]).read_text() == 'license'
    with pytest.raises(components.InstallError, match='already exists'):
        components.install(c, mf, platform, bundle, tmp_path / 'cache', offline=True)


def test_files_components_are_skipped_where_not_listed(tmp_path, fake_tools):
    mf = manifest.load()
    components.install(mf.component('msvc-runtime-arm64'), mf, PLATFORMS['windows-x64'], tmp_path, tmp_path,
                       offline=True)
    assert list(tmp_path.iterdir()) == []
