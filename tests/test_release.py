import hashlib
import json

import pytest

from assembler import manifest, release
from assembler.platforms import archive_name


@pytest.fixture
def dist(tmp_path):
    mf = manifest.load()
    for name in mf.platforms:
        path = tmp_path / archive_name('v1', name)
        path.write_bytes(name.encode())
        digest = hashlib.sha256(name.encode()).hexdigest()
        (tmp_path / (path.name + '.sha256')).write_text(f'{digest}  {path.name}\n')
    return tmp_path


def test_collects_every_platform(dist):
    archives = release.collect_archives(dist, 'v1', manifest.load().platforms)
    assert set(archives) == set(manifest.load().platforms)
    assert archives['windows-x64']['name'].endswith('-windows-x64.zip')
    assert archives['linux-x86_64']['sha256'] == hashlib.sha256(b'linux-x86_64').hexdigest()


def test_rejects_an_archive_that_changed_after_assembly(dist):
    (dist / archive_name('v1', 'darwin-arm64')).write_bytes(b'tampered')
    with pytest.raises(release.ReleaseError, match='does not match'):
        release.collect_archives(dist, 'v1', manifest.load().platforms)


def test_rejects_a_missing_platform(dist):
    (dist / archive_name('v1', 'linux-aarch64')).unlink()
    with pytest.raises(release.ReleaseError, match='linux-aarch64'):
        release.collect_archives(dist, 'v1', manifest.load().platforms)


def test_main_writes_record_sums_and_notes(dist, tmp_path, monkeypatch):
    monkeypatch.setattr(release, '_head_commit', lambda: 'c0ffee')
    image = 'ghcr.io/flipperdevices/flipperone-mcu-toolchain@sha256:' + 'a' * 64
    out = tmp_path / 'out'
    assert release.main(['--dist', str(dist), '--tag', 'v1', '--image', image, '--out', str(out)]) == 0
    record = json.loads((out / 'release.json').read_text())
    assert record['schema'] == 1 and record['tag'] == 'v1' and record['source_commit'] == 'c0ffee'
    name, digest = image.split('@')
    assert record['image'] == {'name': name, 'digest': digest}
    assert record['components']['pico-sdk']['commit'] == manifest.load().component('pico-sdk').raw['commit']
    sums = (out / 'SHA256SUMS').read_text().splitlines()
    assert len(sums) == len(manifest.load().platforms)
    assert all(len(line.split('  ')[0]) == 64 for line in sums)
    assert record['components']['libusb']['platforms'] == ['linux-aarch64', 'linux-x86_64']
    assert record['components']['libgpiod']['platforms'] == ['linux-aarch64']
    assert '(linux-aarch64, linux-x86_64)' in (out / 'release-notes.md').read_text()
    assert image in (out / 'release-notes.md').read_text()


@pytest.mark.parametrize('tag', ['1', 'v0', 'v01', 'dev-abc', 'v1.2'])
def test_release_tags_are_v_and_a_positive_integer(dist, tmp_path, tag):
    with pytest.raises(SystemExit):
        release.main(['--dist', str(dist), '--tag', tag, '--out', str(tmp_path / 'out')])
