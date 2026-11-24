"""The bundle's runtime contract: environment variables and the scripts that set them.

Every script resolves the bundle root from its own location, so a bundle works wherever
it is unpacked. The variable list here is the single definition; the Dockerfile's ENV
block is checked against it by tests/test_env.py.
"""

from __future__ import annotations

from dataclasses import dataclass

from .manifest import Manifest
from .platforms import Platform


@dataclass(frozen=True)
class Var:
    name: str
    value: str  # bundle-relative POSIX path, or a literal
    is_path: bool


def variables(manifest: Manifest, platform: Platform, tag: str) -> list[Var]:
    gcc = manifest.component('arm-none-eabi-gcc').dest
    return [
        Var('FLIPPERONE_TOOLCHAIN', tag, False),
        Var('FLIPPERONE_TOOLCHAIN_ROOT', '.', True),
        Var('PICO_SDK_PATH', manifest.component('pico-sdk').dest, True),
        Var('PICO_TOOLCHAIN_PATH', gcc, True),
        Var('picotool_DIR', manifest.component('picotool').dest, True),
        Var('pioasm_DIR', manifest.component('pioasm').dest, True),
        Var('OPENOCD_SCRIPTS', manifest.component('openocd').dest + '/scripts', True),
        # Overrides the firmware's scripts already read (swd.py, isr_ram_check.py).
        Var('F1_OPENOCD', manifest.component('openocd').exe(platform), True),
        Var('ARM_TOOLCHAIN_BIN', gcc + '/bin', True),
        Var('PYTHONNOUSERSITE', '1', False),
    ]


def path_dirs(manifest: Manifest, platform: Platform) -> list[str]:
    dirs: list[str] = []
    for c in manifest.components:
        dirs.extend(c.path_dirs(platform))
    return dirs


def _join(root: str, rel: str, sep: str) -> str:
    return root if rel == '.' else root + sep + rel.replace('/', sep)


def render_sh(manifest: Manifest, platform: Platform, tag: str) -> str:
    path = ':'.join(_join('$_fo_root', d, '/') for d in path_dirs(manifest, platform))
    exports = '\n'.join(
        f'export {v.name}="{_join("$_fo_root", v.value, "/")}"' if v.is_path else f"export {v.name}='{v.value}'"
        for v in variables(manifest, platform, tag)
    )
    return f'''\
# Flipper One MCU toolchain {tag} ({platform.name}). Source this file from bash or zsh:
#   . /path/to/fbtenv.sh
# It can be sourced again, or after another bundle's fbtenv.sh: PATH keeps one copy.
if [ -n "${{BASH_SOURCE:-}}" ]; then
    _fo_script="${{BASH_SOURCE[0]}}"
    if [ "$_fo_script" = "$0" ]; then
        echo "fbtenv.sh: source this file instead of running it: . $0" >&2
        exit 1
    fi
elif [ -n "${{ZSH_VERSION:-}}" ]; then
    eval '_fo_script="${{(%):-%x}}"'
else
    echo "fbtenv.sh: source this file from bash or zsh" >&2
    return 1 2>/dev/null || exit 1
fi
_fo_root="$(cd "$(dirname "$_fo_script")" && pwd -P)" || return 1
if [ -n "${{_FLIPPERONE_TOOLCHAIN_PATH:-}}" ]; then
    case "$PATH" in
        "$_FLIPPERONE_TOOLCHAIN_PATH":*) PATH="${{PATH#"$_FLIPPERONE_TOOLCHAIN_PATH":}}" ;;
        "$_FLIPPERONE_TOOLCHAIN_PATH") PATH="" ;;
    esac
fi
export _FLIPPERONE_TOOLCHAIN_PATH="{path}"
export PATH="$_FLIPPERONE_TOOLCHAIN_PATH${{PATH:+:$PATH}}"
{exports}
unset _fo_script _fo_root
'''


def render_ps1(manifest: Manifest, platform: Platform, tag: str) -> str:
    path = ', '.join(f"'{d.replace('/', chr(92))}'" for d in path_dirs(manifest, platform))
    lines = []
    for v in variables(manifest, platform, tag):
        if v.is_path:
            value = '$_foRootF' if v.value == '.' else f"$_foRootF + '/{v.value}'"
        else:
            value = f"'{v.value}'"
        lines.append(f'$env:{v.name} = {value}')
    exports = '\n'.join(lines)
    return f'''\
# Flipper One MCU toolchain {tag} ({platform.name}). Dot-source from PowerShell:
#   . C:\\path\\to\\fbtenv.ps1
# If scripts are blocked: powershell -ExecutionPolicy Bypass -NoExit -File C:\\path\\to\\fbtenv.ps1
$_foRoot = $PSScriptRoot
$_foRootF = $_foRoot.Replace('\\', '/')
if ($env:_FLIPPERONE_TOOLCHAIN_PATH -and $env:PATH.StartsWith($env:_FLIPPERONE_TOOLCHAIN_PATH + ';')) {{
    $env:PATH = $env:PATH.Substring($env:_FLIPPERONE_TOOLCHAIN_PATH.Length + 1)
}}
$env:_FLIPPERONE_TOOLCHAIN_PATH = (@({path}) | ForEach-Object {{ Join-Path $_foRoot $_ }}) -join ';'
$env:PATH = $env:_FLIPPERONE_TOOLCHAIN_PATH + ';' + $env:PATH
{exports}
Remove-Variable _foRoot, _foRootF
'''


def render_cmd(manifest: Manifest, platform: Platform, tag: str) -> str:
    path = ';'.join(_join('%_FO_ROOT%', d, '\\') for d in path_dirs(manifest, platform))
    exports = '\n'.join(
        f'set "{v.name}={_join("%_FO_ROOTF%", v.value, "/")}"' if v.is_path else f'set "{v.name}={v.value}"'
        for v in variables(manifest, platform, tag)
    )
    return f'''\
@echo off
rem Flipper One MCU toolchain {tag} ({platform.name}). From cmd.exe:
rem   call C:\\path\\to\\fbtenv.cmd
set "_FO_ROOT=%~dp0"
set "_FO_ROOT=%_FO_ROOT:~0,-1%"
set "_FO_ROOTF=%_FO_ROOT:\\=/%"
if defined _FLIPPERONE_TOOLCHAIN_PATH call set "PATH=%%PATH:%_FLIPPERONE_TOOLCHAIN_PATH%;=%%"
set "_FLIPPERONE_TOOLCHAIN_PATH={path}"
set "PATH=%_FLIPPERONE_TOOLCHAIN_PATH%;%PATH%"
{exports}
set "_FO_ROOT="
set "_FO_ROOTF="
'''.replace('\n', '\r\n')


def render_initial_cache(manifest: Manifest, platform: Platform, tag: str) -> str:
    python = manifest.component('python').exe(platform)
    names = {'PICO_SDK_PATH', 'PICO_TOOLCHAIN_PATH', 'picotool_DIR', 'pioasm_DIR'}
    lines = [
        f'set({v.name} "${{_fo_root}}/{v.value}" CACHE PATH "flipperone-mcu-toolchain {tag}")'
        for v in variables(manifest, platform, tag) if v.name in names
    ]
    lines.append(f'set(Python3_EXECUTABLE "${{_fo_root}}/{python}" CACHE FILEPATH "flipperone-mcu-toolchain {tag}")')
    body = '\n'.join(lines)
    return f'''\
# Flipper One MCU toolchain {tag} ({platform.name}): an initial cache for shells and IDEs
# that do not source fbtenv. Pass it with -C, not as CMAKE_TOOLCHAIN_FILE: the Pico SDK
# needs PICO_SDK_PATH before project(), and picks its own toolchain file.
#   cmake -C <bundle>/cmake/initial-cache.cmake -G Ninja -S <source> -B <build>
get_filename_component(_fo_root "${{CMAKE_CURRENT_LIST_DIR}}/.." ABSOLUTE)
{body}
unset(_fo_root)
'''


def scripts(manifest: Manifest, platform: Platform, tag: str) -> dict[str, str]:
    """Bundle-relative path -> content of every generated script for this platform."""
    out = {'cmake/initial-cache.cmake': render_initial_cache(manifest, platform, tag)}
    if platform.windows:
        out['fbtenv.ps1'] = render_ps1(manifest, platform, tag)
        out['fbtenv.cmd'] = render_cmd(manifest, platform, tag)
    else:
        out['fbtenv.sh'] = render_sh(manifest, platform, tag)
    return out
