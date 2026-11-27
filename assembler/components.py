"""Installers for the component kinds: archive, git, pip, deb and files."""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import shutil
import stat
import subprocess
import tarfile
import tempfile
import zipfile
from pathlib import Path

from .fetch import Mirror, fetch
from .manifest import REPO_ROOT, Component, Manifest
from .platforms import Platform, host_platform
from .unpack import extract, select_root


class InstallError(RuntimeError):
    pass


def run(argv: list[str], cwd: Path | None = None, env: dict | None = None, timeout: int = 900) -> None:
    print('  + ' + ' '.join(str(a) for a in argv), flush=True)
    subprocess.run([str(a) for a in argv], cwd=cwd, env=env, check=True, timeout=timeout)


def rmtree(path: Path) -> None:
    """shutil.rmtree that also removes read-only files (git packs on Windows)."""
    def force(func, target, _exc):
        os.chmod(target, stat.S_IWRITE)
        func(target)
    if path.exists():
        shutil.rmtree(path, onexc=force)


def copy_licenses(tree: Path, patterns: list[str], target: Path) -> None:
    """Copy files under `tree` whose POSIX relative path matches any pattern."""
    for pattern in patterns:
        matched = False
        for path in sorted(tree.rglob('*')):
            rel = path.relative_to(tree).as_posix()
            if path.is_file() and fnmatch.fnmatchcase(rel, pattern):
                out = target / rel
                out.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, out)
                matched = True
        if not matched:
            raise InstallError(f'license pattern {pattern!r} matched nothing in {tree}')


def restamp_pyc_sources(tree: Path) -> int:
    """Give each .py the mtime its timestamp-validated .pyc expects.

    python-build-standalone normalises source mtimes but keeps the build time in .pyc
    headers, so the interpreter would rewrite its own bytecode on every first import (and
    on every start from a read-only install). The header also records the source size;
    only sources whose size matches are re-stamped. Returns how many were.
    """
    count = 0
    for pyc in tree.rglob('__pycache__/*.pyc'):
        with pyc.open('rb') as stream:
            header = stream.read(16)
        if len(header) < 16 or int.from_bytes(header[4:8], 'little') != 0:
            continue  # not timestamp-validated
        mtime = int.from_bytes(header[8:12], 'little')
        size = int.from_bytes(header[12:16], 'little')
        source = pyc.parent.parent / (pyc.name.split('.', 1)[0] + '.py')
        if source.is_file() and source.stat().st_size & 0xFFFFFFFF == size:
            os.utime(source, (mtime, mtime))
            count += 1
    return count


def patchelf(manifest: Manifest, cache: Path, offline: bool, mirror: Mirror | None = None) -> Path:
    """The pinned patchelf for this host, taken from its wheel."""
    asset = manifest.patchelf_asset(host_platform() or 'unsupported')
    wheel = fetch(asset.url, asset.sha256, cache / 'downloads', offline, mirror)
    exe = cache / 'tools' / f'patchelf-{asset.sha256[:16]}' / 'patchelf'
    if not exe.is_file():
        with zipfile.ZipFile(wheel) as zf:
            member = next(n for n in zf.namelist() if n.endswith('.data/scripts/patchelf'))
            exe.parent.mkdir(parents=True, exist_ok=True)
            partial = exe.with_name('patchelf.part')
            partial.write_bytes(zf.read(member))
            partial.chmod(0o755)
            os.replace(partial, exe)
    return exe


def set_runpath(tool: Path, binary: Path, runpath: str) -> None:
    run([tool, '--set-rpath', runpath, binary])


def install_archive(c: Component, manifest: Manifest, platform: Platform, bundle: Path, cache: Path,
                    offline: bool, mirror: Mirror | None = None) -> None:
    asset = c.asset(platform)
    archive = fetch(asset.url, asset.sha256, cache / 'downloads', offline, mirror)
    target = bundle / c.dest
    if target.exists():
        raise InstallError(f'{c.name}: {target} already exists')
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=bundle.parent, prefix='.unpack-') as tmp:
        tree = Path(tmp) / 'tree'
        extract(archive, tree, asset.exclude)
        copy_licenses(tree, c.license_files, bundle / 'licenses' / c.name)
        if c.raw.get('restamp_pyc'):
            print(f'  re-stamped {restamp_pyc_sources(tree)} sources to match their .pyc', flush=True)
        os.replace(select_root(tree, asset.root), target)
    if c.raw.get('runpath') and platform.os == 'linux':
        set_runpath(patchelf(manifest, cache, offline, mirror), bundle / c.exe(platform), c.raw['runpath'])


def install_deb(c: Component, manifest: Manifest, platform: Platform, bundle: Path, cache: Path,
                offline: bool, mirror: Mirror | None = None) -> None:
    """Copy the listed libraries out of a Debian package; each finds its siblings in `dest`."""
    asset = c.asset(platform)
    package = fetch(asset.url, asset.sha256, cache / 'downloads', offline, mirror)
    target = bundle / c.dest
    target.mkdir(parents=True, exist_ok=True)
    tool = patchelf(manifest, cache, offline, mirror)
    with tempfile.TemporaryDirectory(dir=bundle.parent, prefix='.unpack-') as tmp:
        tree = Path(tmp) / 'tree'
        extract(package, tree)
        copy_licenses(tree, c.license_files, bundle / 'licenses' / c.name)
        for name, member in asset.files:
            source = tree / member
            if source.is_symlink() or not source.is_file():
                raise InstallError(f'{c.name}: {member} is not a regular file in {asset.filename}')
            out = target / name
            if out.exists():
                raise InstallError(f'{c.name}: {out} already exists')
            shutil.copyfile(source, out)
            out.chmod(0o644)
            set_runpath(tool, out, '$ORIGIN')


def install_files(c: Component, manifest: Manifest, platform: Platform, bundle: Path, cache: Path,
                  offline: bool, mirror: Mirror | None = None) -> None:
    """Copy the listed members of a package into earlier components, e.g. runtime DLLs."""
    asset = c.asset(platform)
    package = fetch(asset.url, asset.sha256, cache / 'downloads', offline, mirror)
    with tempfile.TemporaryDirectory(dir=bundle.parent, prefix='.unpack-') as tmp:
        tree = Path(tmp) / 'tree'
        extract(package, tree)
        copy_licenses(tree, c.license_files, bundle / 'licenses' / c.name)
        for target, member in asset.files:
            source = tree / member
            if source.is_symlink() or not source.is_file():
                raise InstallError(f'{c.name}: {member} is not a regular file in {asset.filename}')
            out = bundle / target
            if not out.parent.is_dir():
                raise InstallError(f'{c.name}: {out.parent} does not exist')
            if out.exists():
                raise InstallError(f'{c.name}: {out} already exists')
            shutil.copyfile(source, out)
            out.chmod(0o644)


def _git(args: list[str], cwd: Path) -> str:
    argv = ['git', '-c', 'core.autocrlf=false', '-c', 'core.eol=lf', '-c', 'advice.detachedHead=false', *args]
    return subprocess.run(argv, cwd=cwd, check=True, timeout=900, capture_output=True, text=True).stdout.strip()


def _git_checkout(url: str, commit: str, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    print(f'  git {url} @ {commit}', flush=True)
    _git(['init', '-q'], dest)
    _git(['remote', 'add', 'origin', url], dest)
    _git(['fetch', '-q', '--depth', '1', 'origin', commit], dest)
    _git(['checkout', '-q', 'FETCH_HEAD'], dest)
    head = _git(['rev-parse', 'HEAD'], dest)
    if head != commit:
        raise InstallError(f'{url}: checked out {head}, expected {commit}')


def keep_only(root: Path, keep: list[str]) -> None:
    """Delete everything under `root` except the listed files (and their parent dirs)."""
    kept = {}
    for rel in keep:
        path = root / rel
        if not path.is_file():
            raise InstallError(f'{root}: file to keep is missing: {rel}')
        kept[rel] = path.read_bytes(), path.stat().st_mode
    rmtree(root)
    for rel, (data, mode) in kept.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        path.chmod(mode & 0o777)


def install_git(c: Component, bundle: Path, cache: Path, offline: bool) -> None:
    """Shallow checkout at the pinned commit; only the pinned submodules, each verified.

    `keep` maps a submodule path to the only files to retain from it, for submodules the
    bundle needs only a few files of (see the manifest and README).
    """
    submodules: dict[str, str] = c.raw.get('submodules', {})
    keep: dict[str, list[str]] = c.raw.get('keep', {})
    key = c.raw['commit'] + ''.join(f'-{s[:12]}' for s in submodules.values())
    if keep:
        key += '-keep' + hashlib.sha256(json.dumps(keep, sort_keys=True).encode()).hexdigest()[:12]
    cached = cache / 'git' / f'{c.name}-{key}-v2.tar'  # bump the suffix when the cache format changes
    target = bundle / c.dest
    if target.exists():
        raise InstallError(f'{c.name}: {target} already exists')
    if not cached.is_file():
        if offline:
            raise InstallError(f'offline and not cached: {c.name} ({cached})')
        with tempfile.TemporaryDirectory(dir=bundle.parent, prefix='.git-') as tmp:
            tree = Path(tmp) / 'tree'
            _git_checkout(c.raw['url'], c.raw['commit'], tree)
            for path, commit in submodules.items():
                listing = _git(['ls-tree', 'HEAD', path], tree).split()
                if listing[:3] != ['160000', 'commit', commit]:
                    raise InstallError(f'{c.name}: submodule {path} is {listing}, manifest pins {commit}')
                name = _git(['config', '-f', '.gitmodules', '--get-regexp', r'^submodule\..*\.path$'], tree)
                section = next(line.split()[0] for line in name.splitlines() if line.split()[1] == path)
                url = _git(['config', '-f', '.gitmodules', '--get', section[:-len('.path')] + '.url'], tree)
                _git_checkout(url, commit, tree / path)
                rmtree(tree / path / '.git')
                if path in keep:
                    keep_only(tree / path, keep[path])
            # Checkout times differ per clone; the commit time does not.
            stamp = int(_git(['show', '-s', '--format=%ct', 'HEAD'], tree))
            rmtree(tree / '.git')
            no_follow = os.utime in os.supports_follow_symlinks  # not on Windows
            for path in [tree, *tree.rglob('*')]:
                if no_follow or not path.is_symlink():
                    os.utime(path, (stamp, stamp), follow_symlinks=not no_follow)
            cached.parent.mkdir(parents=True, exist_ok=True)
            partial = cached.with_name(cached.name + '.part')
            with tarfile.open(partial, 'w') as tar:
                tar.add(tree, arcname='.')
            os.replace(partial, cached)
    target.mkdir(parents=True)
    with tarfile.open(cached) as tar:
        tar.extractall(target, filter='data')
    copy_licenses(target, c.license_files, bundle / 'licenses' / c.name)


def _script_files(interpreter_root: Path) -> set[Path]:
    return {p for d in ('bin', 'Scripts') if (interpreter_root / d).is_dir() for p in (interpreter_root / d).iterdir()}


def drop_console_scripts(interpreter_root: Path, scripts: set[Path]) -> None:
    """Remove pip-generated console scripts and their RECORD lines.

    pip writes the interpreter's absolute path into each script's shebang (and into the
    .exe launchers on Windows), which breaks both relocation and reproducibility. The
    packages are meant to be run as modules (python -m ...), not through the scripts.
    """
    for script in scripts:
        print(f'  drop console script {script.relative_to(interpreter_root)}', flush=True)
        script.unlink()
    resolved = {s.resolve() for s in scripts}
    for record in interpreter_root.glob('**/site-packages/*.dist-info/RECORD'):
        site = record.parent.parent
        lines = record.read_text(encoding='utf-8').splitlines(keepends=True)
        kept = [line for line in lines if (site / line.split(',', 1)[0]).resolve() not in resolved]
        if kept != lines:
            record.write_text(''.join(kept), encoding='utf-8')


def install_pip(c: Component, manifest: Manifest, platform: Platform, bundle: Path, cache: Path,
                offline: bool) -> None:
    """Install the hash-locked wheels into the bundled interpreter, natively."""
    if host_platform() != platform.name:
        raise InstallError(f'{c.name}: pip components install natively; host is {host_platform()}, '
                           f'target is {platform.name}')
    python = bundle / manifest.component(c.raw['interpreter']).exe(platform)
    requirements = REPO_ROOT / c.raw['requirements']
    wheels = cache / 'wheels'
    env = {k: v for k, v in os.environ.items() if not k.startswith(('PIP_', 'PYTHON'))}
    env.update(PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1', PIP_CONFIG_FILE=os.devnull,
               PIP_DISABLE_PIP_VERSION_CHECK='1', PIP_NO_INPUT='1')
    common = ['--only-binary=:all:', '--no-deps', '--require-hashes', '-r', requirements]
    if not offline:
        wheels.mkdir(parents=True, exist_ok=True)
        run([python, '-m', 'pip', 'download', '-q', '-d', wheels, *common], env=env)
    interpreter_root = bundle / manifest.component(c.raw['interpreter']).dest
    before = _script_files(interpreter_root)
    run([python, '-m', 'pip', 'install', '-q', '--no-index', '--find-links', wheels, '--no-compile',
         '--no-warn-script-location', *common], env=env)
    drop_console_scripts(interpreter_root, _script_files(interpreter_root) - before)


def install(c: Component, manifest: Manifest, platform: Platform, bundle: Path, cache: Path,
            offline: bool, mirror: Mirror | None = None) -> None:
    if not c.applies_to(platform):
        print(f'  not for {platform.name}', flush=True)
    elif c.kind == 'archive':
        install_archive(c, manifest, platform, bundle, cache, offline, mirror)
    elif c.kind == 'deb':
        install_deb(c, manifest, platform, bundle, cache, offline, mirror)
    elif c.kind == 'files':
        install_files(c, manifest, platform, bundle, cache, offline, mirror)
    elif c.kind == 'git':
        install_git(c, bundle, cache, offline)
    elif c.kind == 'pip':
        install_pip(c, manifest, platform, bundle, cache, offline)
    else:
        raise InstallError(f'{c.name}: unknown kind {c.kind}')
