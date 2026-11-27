"""Smoke-test an unpacked bundle from a shell where its fbtenv script has been sourced.

    . <bundle>/fbtenv.sh && python3 tests/smoke/run.py

Checks, in order: the bundle is the one this repo's manifest describes and its files match
SHA256SUMS; the env script set every variable and put each tool dir on PATH; every tool
reports its pinned version; on Linux, the tools load the bundled USB libraries, not the
system's; a minimal RP2350 project (tests/smoke/blink) builds using the prebuilt pioasm
and picotool, once with the env and once with only cmake/initial-cache.cmake, and clangd
parses it with the bundled GCC's headers. In a container whose ENV already holds the
variables, run it without sourcing anything.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from assembler import env, manifest  # noqa: E402
from assembler.platforms import PLATFORMS  # noqa: E402

BLINK = Path(__file__).resolve().parent / 'blink'
MAX_RELATIVE_PATH = 160  # Windows MAX_PATH headroom below %LOCALAPPDATA%\flipperone-mcu-toolchain\<tag>\


class SmokeFailure(AssertionError):
    pass


def check(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeFailure(message)
    print(f'  ok  {message}', flush=True)


def same_path(a: str | Path, b: str | Path) -> bool:
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


def run(argv: list, cwd: Path | None = None, env_: dict | None = None, timeout: int = 1800) -> str:
    print('  + ' + ' '.join(str(a) for a in argv), flush=True)
    result = subprocess.run([str(a) for a in argv], cwd=cwd, env=env_, timeout=timeout,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors='replace')
    if result.returncode != 0:
        print(result.stdout)
        raise SmokeFailure(f'{argv[0]} exited with {result.returncode}')
    return result.stdout


def check_identity(root: Path, mf: manifest.Manifest) -> dict:
    print('[identity]')
    record = json.loads((root / 'toolchain.json').read_text())
    check(record['manifest_sha256'] == mf.sha256, 'bundle was assembled from this manifest')
    sums = (root / 'SHA256SUMS').read_text().splitlines()
    bad = []
    for line in sums:
        digest, rel = line.split('  ', 1)
        with (root / rel).open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != digest:
                bad.append(rel)
    check(not bad, f'{len(sums)} files match SHA256SUMS' + (f' (mismatch: {bad[:5]})' if bad else ''))
    longest = max((p for p in root.rglob('*')), key=lambda p: len(p.relative_to(root).as_posix()))
    length = len(longest.relative_to(root).as_posix())
    check(length <= MAX_RELATIVE_PATH, f'longest relative path is {length} chars (limit {MAX_RELATIVE_PATH})')
    return record


def check_env(root: Path, mf: manifest.Manifest, platform, tag: str) -> None:
    print('[env]')
    for var in env.variables(mf, platform, tag):
        value = os.environ.get(var.name)
        if var.is_path:
            check(value is not None and same_path(value, root / var.value), f'{var.name} -> {var.value}')
        else:
            check(value == var.value, f'{var.name} = {var.value}')
    path = os.environ['PATH'].split(os.pathsep)
    dirs = env.path_dirs(mf, platform)
    check(all(same_path(p, root / d) for p, d in zip(path, dirs, strict=False)),
          f'PATH starts with the {len(dirs)} bundle dirs, in manifest order')


def check_tools(root: Path, mf: manifest.Manifest, platform) -> None:
    print('[tools]')
    for c in mf.components:
        spec = c.raw.get('check')
        if not spec:
            continue
        rel = mf.component(c.raw['interpreter']).exe(platform) if c.kind == 'pip' else c.exe(platform)
        exe = root / rel
        if c.kind != 'pip':
            found = shutil.which(Path(rel).name)
            check(found is not None and same_path(found, exe), f'{Path(rel).name} on PATH is the bundled one')
        script = [REPO / spec['script']] if 'script' in spec else []
        output = run([exe, *script, *spec.get('args', [])])
        check(spec['expect'] in output, f'{c.name}: output contains {spec["expect"]!r}')


def check_libraries(root: Path, mf: manifest.Manifest, platform) -> None:
    """Every library a tool needs resolves (ldd); with a runpath, the bundled ones from the bundle."""
    print('[libraries]')
    bundled = {name: root / c.dest / name for c in mf.components
               if c.kind == 'deb' and c.applies_to(platform) for name, _ in c.asset(platform).files}
    for c in mf.components:
        if c.kind != 'archive' or not c.raw.get('exe') or not c.applies_to(platform):
            continue
        if not c.raw.get('runpath'):
            # Self-contained tools, e.g. OpenOCD with static USB libraries
            result = subprocess.run(['ldd', str(root / c.exe(platform))], capture_output=True, text=True)
            if 'not a dynamic executable' not in result.stdout + result.stderr:
                check('not found' not in result.stdout, f'{c.name}: ldd finds every library')
            continue
        output = run(['ldd', root / c.exe(platform)])
        check('not found' not in output, f'{c.name}: ldd finds every library')
        resolved = {}
        for line in output.splitlines():
            if ' => /' in line:  # "\tname => /path (0x...)"; the path may hold spaces
                name, target = line.strip().split(' => ', 1)
                resolved[name] = target.rsplit(' (', 1)[0]
        used = sorted(set(resolved) & set(bundled))
        check(bool(used) and all(same_path(resolved[n], bundled[n]) for n in used),
              f'{c.name}: {", ".join(used)} from the bundle')


def cache_value(build: Path, name: str) -> str | None:
    for line in (build / 'CMakeCache.txt').read_text().splitlines():
        if line.startswith(name + ':'):
            return line.split('=', 1)[1]
    return None


def build_blink(root: Path, work: Path, use_env: bool) -> str:
    """Build the RP2350 smoke project; returns the sha256 of its blink.uf2."""
    label = 'env' if use_env else 'initial-cache'
    print(f'[blink via {label}]')
    build = work / f'blink-{label}'
    child_env = dict(os.environ)
    args = ['cmake', '-G', 'Ninja', '-S', BLINK, '-B', build, '-DCMAKE_BUILD_TYPE=Release']
    if not use_env:
        for name in ('PICO_SDK_PATH', 'PICO_TOOLCHAIN_PATH', 'picotool_DIR', 'pioasm_DIR'):
            child_env.pop(name, None)
        args[1:1] = ['-C', root / 'cmake' / 'initial-cache.cmake']
    run(args, env_=child_env)
    run(['cmake', '--build', build], env_=child_env)
    uf2 = build / 'blink.uf2'
    check(uf2.is_file(), 'blink.uf2 built (picotool ran)')
    for name, rel in (('pioasm_DIR', 'tools/pioasm'), ('picotool_DIR', 'tools/picotool')):
        value = cache_value(build, name)
        check(value is not None and same_path(value, root / rel), f'{name} is the bundled {rel}')
    check(not (build / 'pioasm').exists() and not (build / '_deps' / 'picotool-src').exists(),
          'pioasm and picotool were not built from source')
    if use_env:
        check_clangd(root, build)
    with uf2.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def check_clangd(root: Path, build: Path) -> None:
    """clangd reads the build's compile commands and the Arm GCC's system headers."""
    gcc = root / 'tools' / 'arm-none-eabi-gcc' / 'bin'
    # Any name in that directory: with a space in its path, CMake on Windows records the
    # compiler by its 8.3 short name (ARxxxx~1.EXE), which 'arm-none-eabi-*' misses
    output = run(['clangd', f'--check={BLINK / "blink.c"}', f'--compile-commands-dir={build}',
                  f'--query-driver={gcc.as_posix()}/*'])
    check('All checks completed, 0 errors' in output, 'clangd parses blink.c without errors')


def report(platform, digest: str) -> None:
    """blink.uf2's hash, for comparing builds across platforms."""
    print(f'  blink.uf2  {digest}')
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as out:
            out.write(f'| Platform | blink.uf2 sha256 |\n|---|---|\n| {platform.name} | `{digest}` |\n')


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--skip-blink', action='store_true')
    parser.add_argument('--work', type=Path, help='build directory (default: a temporary one)')
    args = parser.parse_args(argv)

    root_env = os.environ.get('FLIPPERONE_TOOLCHAIN_ROOT')
    if not root_env:
        parser.error('source the bundle fbtenv script first')
    root = Path(root_env).resolve()
    mf = manifest.load()
    record = check_identity(root, mf)
    platform = PLATFORMS[record['platform']]
    check_env(root, mf, platform, record['tag'])
    check_tools(root, mf, platform)
    if platform.os == 'linux':
        check_libraries(root, mf, platform)
    with tempfile.TemporaryDirectory(prefix='fo-smoke-') as tmp:
        work = args.work.resolve() if args.work else Path(tmp)
        work.mkdir(parents=True, exist_ok=True)
        if not args.skip_blink:
            digest = build_blink(root, work, use_env=True)
            build_blink(root, work, use_env=False)
            report(platform, digest)
    print('[smoke] passed')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except SmokeFailure as failure:
        print(f'[smoke] FAILED: {failure}', file=sys.stderr)
        raise SystemExit(1) from None
