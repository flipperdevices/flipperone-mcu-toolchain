import copy
import json

import pytest

from assembler import manifest
from assembler.platforms import PLATFORMS


@pytest.fixture(scope='module')
def data():
    return json.loads(manifest.MANIFEST.read_text())


def test_manifest_is_valid(data):
    assert manifest.validate(data) == []
    manifest.load()


def deb(data):
    return next(c for c in data['components'] if c['kind'] == 'deb')


def tool(data, name):
    return next(c for c in data['components'] if c['name'] == name)


def test_deb_components_share_their_dest(data):
    debs = [c for c in data['components'] if c['kind'] == 'deb']
    assert len(debs) > 1 and len({c['dest'] for c in debs}) == 1


def test_every_archive_component_covers_every_platform():
    mf = manifest.load()
    for c in mf.components:
        if c.kind == 'archive':
            for name in mf.platforms:
                asset = c.asset(PLATFORMS[name])
                assert asset.url.startswith('https://')


def test_no_url_is_used_twice(data):
    urls = [spec['url'] for c in data['components'] if c['kind'] == 'archive' for spec in c['assets'].values()]
    assert len(urls) == len(set(urls))


def test_components_the_env_contract_needs_exist():
    mf = manifest.load()
    for name in ('arm-none-eabi-gcc', 'pico-sdk', 'picotool', 'pioasm', 'openocd', 'python'):
        mf.component(name)


def test_every_tool_has_a_version_check(data):
    for c in data['components']:
        if c['kind'] in ('archive', 'pip') and 'exe' in c or c['kind'] == 'pip':
            assert c.get('check', {}).get('expect'), c['name']


@pytest.mark.parametrize('mutate, message', [
    (lambda d: d['components'].append(copy.deepcopy(d['components'][0])), 'duplicate name'),
    (lambda d: d['components'][0]['assets']['linux-x86_64'].update(sha256='abc'), 'sha256'),
    (lambda d: d['components'][0]['assets']['linux-x86_64'].update(url='http://x/y'), 'https'),
    (lambda d: d['components'][0]['assets'].pop('windows-x64'), 'no asset for windows-x64'),
    (lambda d: d['components'][0].update(dest='../outside'), 'dest'),
    (lambda d: d['components'][1].update(dest='tools/arm-none-eabi-gcc/sdk'), 'overlaps'),
    (lambda d: d['components'][1].update(commit='2.3.1'), 'commit'),
    (lambda d: d.update(platforms=['linux-x86_64', 'beos-m68k']), 'platforms'),
    (lambda d: d['components'][1].update(keep={'lib/lwip': ['x']}), 'not a pinned submodule'),
    (lambda d: d['components'][0]['assets']['linux-x86_64'].update(exclude='x'), 'exclude'),
    (lambda d: d['components'][1].update(keep={'lib/tinyusb': ['../x']}), 'relative paths'),
    (lambda d: deb(d)['assets'].update({'darwin-arm64': deb(d)['assets']['linux-x86_64']}), 'deb assets are for'),
    (lambda d: deb(d)['assets']['linux-x86_64'].update(files={}), 'files missing'),
    (lambda d: deb(d)['assets']['linux-x86_64'].update(files={'x.so': 'usr/lib/x.so'}), 'bad file'),
    (lambda d: deb(d)['assets']['linux-x86_64'].update(files={'libx.so.1': '../x'}), 'bad file'),
    (lambda d: deb(d).update(dest='tools/picotool'), 'overlaps'),
    (lambda d: tool(d, 'picotool').update(runpath='/usr/lib'), 'runpath must start with $ORIGIN'),
    (lambda d: tool(d, 'pico-sdk').update(runpath='$ORIGIN'), 'runpath needs an archive component'),
    (lambda d: d.pop('patchelf'), 'runpath needs a patchelf pin'),
    (lambda d: d['patchelf']['assets']['linux-x86_64'].update(sha256='x'), 'patchelf/linux-x86_64: sha256'),
    (lambda d: tool(d, 'python-packages')['check'].update(script='python/nope.py'), 'check script missing'),
    (lambda d: tool(d, 'cmake')['check'].update(expect=''), 'check needs a non-empty expect'),
])
def test_validate_rejects(data, mutate, message):
    broken = copy.deepcopy(data)
    mutate(broken)
    errors = manifest.validate(broken)
    assert any(message in e for e in errors), errors
