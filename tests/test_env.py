import os
import re
import shutil
import subprocess

import pytest

from assembler import env, manifest
from assembler.platforms import PLATFORMS

TAG = 'dev-test'
DOCKER_ROOT = '/opt/flipperone-mcu-toolchain'
SHELLS = [s for s in ('bash', 'zsh') if shutil.which(s)]


@pytest.fixture(scope='module')
def mf():
    return manifest.load()


def fake_bundle(root, mf, platform_name='linux-x86_64'):
    platform = PLATFORMS[platform_name]
    for rel, content in env.scripts(mf, platform, TAG).items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(content)
    for d in env.path_dirs(mf, platform):
        (root / d).mkdir(parents=True, exist_ok=True)
    return root


def sourced_env(shell, script, times=1, before=''):
    sources = '; '.join([f'. "{script}"'] * times)
    out = subprocess.run([shell, '-c', f'{before}{sources}; env'], check=True, capture_output=True, text=True,
                         env={'PATH': '/usr/bin:/bin', 'HOME': os.environ.get('HOME', '/tmp')}).stdout
    return dict(line.split('=', 1) for line in out.splitlines() if '=' in line)


@pytest.mark.skipif(not SHELLS, reason='no bash or zsh')
@pytest.mark.parametrize('shell', SHELLS)
def test_sh_sets_every_variable(tmp_path, mf, shell):
    root = fake_bundle(tmp_path / 'bundle dir', mf).resolve()
    values = sourced_env(shell, root / 'fbtenv.sh')
    platform = PLATFORMS['linux-x86_64']
    for var in env.variables(mf, platform, TAG):
        expected = str(root) if var.value == '.' else (f'{root}/{var.value}' if var.is_path else var.value)
        assert values[var.name] == expected
    prefix = ':'.join(f'{root}/{d}' for d in env.path_dirs(mf, platform))
    assert values['PATH'] == prefix + ':/usr/bin:/bin'


@pytest.mark.skipif(not SHELLS, reason='no bash or zsh')
@pytest.mark.parametrize('shell', SHELLS)
def test_sh_is_idempotent_and_switches_bundles(tmp_path, mf, shell):
    one = fake_bundle(tmp_path / 'one', mf).resolve()
    two = fake_bundle(tmp_path / 'two', mf).resolve()
    again = sourced_env(shell, one / 'fbtenv.sh', times=3)
    assert again['PATH'].count(str(one)) == len(env.path_dirs(mf, PLATFORMS['linux-x86_64']))
    switched = sourced_env(shell, two / 'fbtenv.sh', before=f'. "{one}/fbtenv.sh"; ')
    assert str(one) not in switched['PATH']
    assert switched['FLIPPERONE_TOOLCHAIN_ROOT'] == str(two)


@pytest.mark.skipif(not shutil.which('bash'), reason='no bash')
def test_sh_refuses_to_run_as_a_program(tmp_path, mf):
    root = fake_bundle(tmp_path / 'b', mf)
    result = subprocess.run(['bash', str(root / 'fbtenv.sh')], capture_output=True, text=True)
    assert result.returncode == 1
    assert 'source this file' in result.stderr


def test_windows_scripts_cover_every_variable(mf):
    platform = PLATFORMS['windows-x64']
    scripts = env.scripts(mf, platform, TAG)
    assert set(scripts) == {'cmake/initial-cache.cmake', 'fbtenv.ps1', 'fbtenv.cmd'}
    for var in env.variables(mf, platform, TAG):
        assert f'$env:{var.name} = ' in scripts['fbtenv.ps1']
        assert f'set "{var.name}=' in scripts['fbtenv.cmd']
    assert '\r\n' in scripts['fbtenv.cmd'] and '\n' not in scripts['fbtenv.cmd'].replace('\r\n', '')
    assert "F1_OPENOCD = $_foRootF + '/tools/openocd/openocd.exe'" in scripts['fbtenv.ps1']
    for d in env.path_dirs(mf, platform):
        assert d.replace('/', '\\') in scripts['fbtenv.cmd']


@pytest.mark.skipif(not shutil.which('pwsh'), reason='no pwsh')
def test_ps1_runs(tmp_path, mf):
    root = fake_bundle(tmp_path / 'b', mf, 'windows-x64')
    out = subprocess.run(['pwsh', '-NoProfile', '-Command',
                          f'. "{root}/fbtenv.ps1"; . "{root}/fbtenv.ps1"; $env:PICO_SDK_PATH; $env:PATH'],
                         check=True, capture_output=True, text=True).stdout.splitlines()
    assert out[0].endswith('/pico-sdk')
    assert out[1].count('arm-none-eabi-gcc') == 1


def test_initial_cache_sets_sdk_paths(mf):
    text = env.scripts(mf, PLATFORMS['darwin-arm64'], TAG)['cmake/initial-cache.cmake']
    for name in ('PICO_SDK_PATH', 'PICO_TOOLCHAIN_PATH', 'picotool_DIR', 'pioasm_DIR', 'Python3_EXECUTABLE'):
        assert re.search(rf'^set\({name} "\$\{{_fo_root}}/', text, re.M), name
    assert 'tools/python/bin/python3' in text
    assert 'python.exe' in env.scripts(mf, PLATFORMS['windows-x64'], TAG)['cmake/initial-cache.cmake']


def test_dockerfile_env_matches_the_contract(mf):
    dockerfile = (manifest.REPO_ROOT / 'docker' / 'Dockerfile').read_text()
    block = dockerfile[dockerfile.index('\nENV ') + 5:]
    block = block[:block.index('\n\n')]
    values = dict(re.findall(r'(\w+)=(\S+)', block.replace('\\\n', ' ')))
    platform = PLATFORMS['linux-x86_64']
    expected = {}
    for var in env.variables(mf, platform, TAG):
        if var.name == 'FLIPPERONE_TOOLCHAIN':
            expected[var.name] = '${TOOLCHAIN_TAG}'
        elif var.is_path:
            expected[var.name] = DOCKER_ROOT if var.value == '.' else f'{DOCKER_ROOT}/{var.value}'
        else:
            expected[var.name] = var.value
    path = values.pop('PATH')
    assert values == expected
    prefix = ':'.join(f'{DOCKER_ROOT}/{d}' for d in env.path_dirs(mf, platform))
    assert path.startswith(prefix + ':/usr/local/sbin:')
