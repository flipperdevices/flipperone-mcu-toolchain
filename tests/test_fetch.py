import hashlib
import urllib.request

import pytest

from assembler import fetch, manifest, mirror

DATA = b'upstream archive'
SHA = hashlib.sha256(DATA).hexdigest()
URL = 'https://example.invalid/releases/tool%2Bdev-1.0.tar.gz'


@pytest.fixture
def fake_net(monkeypatch):
    """Upstream and mirror downloads served from dicts: url -> bytes, or an exception."""
    served: dict[str, object] = {}

    def download(request, target, attempts=4, timeout=120):
        body = served.get(request.full_url, fetch.FetchError(f'{request.full_url}: HTTP 404'))
        if isinstance(body, Exception):
            raise body
        target.write_bytes(body)

    monkeypatch.setattr(fetch, '_download', download)
    fetch.mirror_assets.cache_clear()
    return served


def test_upstream_is_used_and_cached(tmp_path, fake_net):
    fake_net[URL] = DATA
    path = fetch.fetch(URL, SHA, tmp_path)
    assert path.read_bytes() == DATA and path.name == 'tool+dev-1.0.tar.gz'
    del fake_net[URL]
    assert fetch.fetch(URL, SHA, tmp_path, offline=True) == path


def test_mirror_stands_in_when_upstream_is_gone(tmp_path, fake_net, monkeypatch):
    m = fetch.Mirror('o/r', 'mirror')
    monkeypatch.setattr(fetch, 'mirror_assets', lambda _: {f'{SHA}-tool+dev-1.0.tar.gz': 'https://api.github.com/a/1'})
    fake_net['https://api.github.com/a/1'] = DATA
    assert fetch.fetch(URL, SHA, tmp_path, mirror=m).read_bytes() == DATA


def test_mirror_stands_in_when_upstream_changed(tmp_path, fake_net, monkeypatch):
    fake_net[URL] = b'replaced upstream'
    monkeypatch.setattr(fetch, 'mirror_assets', lambda _: {f'{SHA}-tool+dev-1.0.tar.gz': 'https://api.github.com/a/1'})
    fake_net['https://api.github.com/a/1'] = DATA
    assert fetch.fetch(URL, SHA, tmp_path, mirror=fetch.Mirror('o/r', 'm')).read_bytes() == DATA


def test_a_bad_mirror_copy_is_rejected(tmp_path, fake_net, monkeypatch):
    monkeypatch.setattr(fetch, 'mirror_assets', lambda _: {f'{SHA}-tool+dev-1.0.tar.gz': 'https://api.github.com/a/1'})
    fake_net['https://api.github.com/a/1'] = b'not it'
    with pytest.raises(fetch.FetchError, match='sha256 mismatch'):
        fetch.fetch(URL, SHA, tmp_path, mirror=fetch.Mirror('o/r', 'm'))


def test_no_mirror_copy_reports_both_failures(tmp_path, fake_net, monkeypatch):
    monkeypatch.setattr(fetch, 'mirror_assets', lambda _: {})
    with pytest.raises(fetch.FetchError, match='HTTP 404[\\s\\S]*mirror has no'):
        fetch.fetch(URL, SHA, tmp_path, mirror=fetch.Mirror('o/r', 'm'))


@pytest.mark.parametrize('value', ['o/r', 'r@tag', 'o/r/x@tag', 'o/r@'])
def test_mirror_spec_is_owner_repo_at_tag(value):
    with pytest.raises(ValueError):
        fetch.Mirror.parse(value)
    assert fetch.Mirror.parse('o/r@mirror') == fetch.Mirror('o/r', 'mirror')


def test_authorization_is_dropped_on_cross_host_redirect():
    handler = fetch._DropAuthOnRedirect()
    request = urllib.request.Request('https://api.github.com/repos/o/r/releases/assets/1',
                                     headers={'Authorization': 'Bearer t'})
    same = handler.redirect_request(request, None, 302, 'Found', {}, 'https://api.github.com/other')
    other = handler.redirect_request(request, None, 302, 'Found', {}, 'https://objects.githubusercontent.com/x')
    assert same.get_header('Authorization') == 'Bearer t'
    assert other.get_header('Authorization') is None


def test_token_is_sent_only_to_the_github_api(monkeypatch):
    monkeypatch.setenv('GITHUB_TOKEN', 't')
    assert fetch._request('https://api.github.com/x').get_header('Authorization') == 'Bearer t'
    assert fetch._request('https://github.com/o/r/releases/download/v/f').get_header('Authorization') is None


def test_mirror_wants_every_archive_deb_and_patchelf_asset_under_a_unique_name():
    mf = manifest.load()
    names = mirror.wanted(mf)
    expected = sum(len(c.all_assets()) for c in mf.components if c.kind in ('archive', 'deb'))
    expected += len(mf.patchelf['assets'])
    assert len(names) == expected
    assert all(name.split('-', 1)[0] == sha for name, (_, sha) in names.items())
