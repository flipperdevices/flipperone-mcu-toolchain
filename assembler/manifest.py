"""manifest.json: the single source of truth for what goes into a bundle.

Components install in manifest order. Kinds:
- archive: a per-platform (or "any") upstream archive, unpacked into `dest`.
- git: a repository at a pinned commit, with pinned submodules, copied without .git.
- pip: hash-locked wheels installed into the interpreter of another component.
- deb: shared libraries taken from a Debian package, for the platforms it lists. Several
  deb components can share one `dest`.

`patchelf` pins the patchelf wheel, per host, that points Linux binaries at their
bundled libraries (`runpath`).
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from .platforms import PLATFORMS, Platform

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = REPO_ROOT / 'manifest.json'

SHA256_RE = re.compile(r'[0-9a-f]{64}')
COMMIT_RE = re.compile(r'[0-9a-f]{40}')
KINDS = ('archive', 'git', 'pip', 'deb')
LINUX_PLATFORMS = ('linux-x86_64', 'linux-aarch64')
SONAME_RE = re.compile(r'lib[A-Za-z0-9_.+-]+\.so(\.[0-9]+)*')


class ManifestError(ValueError):
    pass


@dataclass(frozen=True)
class Asset:
    url: str
    sha256: str
    root: str | None = None  # path inside the archive to install; None = auto-detect
    exclude: tuple[str, ...] = ()  # archive members to skip (fnmatch patterns)
    files: tuple[tuple[str, str], ...] = ()  # deb: (installed name, member path)

    @property
    def filename(self) -> str:
        return urllib.parse.unquote(self.url.rsplit('/', 1)[-1])


@dataclass(frozen=True)
class Component:
    name: str
    kind: str
    version: str
    license: str
    homepage: str
    dest: str
    raw: dict = field(repr=False, compare=False)

    def asset(self, platform: Platform) -> Asset:
        assets = self.raw['assets']
        spec = assets.get(platform.name, assets.get('any'))
        if spec is None:
            raise ManifestError(f'{self.name}: no asset for {platform.name}')
        # {"same_as": "<platform>"}: deliberately the other platform's archive
        return self._asset(assets[spec['same_as']] if 'same_as' in spec else spec)

    def _asset(self, spec: dict) -> Asset:
        return Asset(url=spec['url'], sha256=spec['sha256'], root=spec.get('root', self.raw.get('root')),
                     exclude=tuple(spec.get('exclude', ())), files=tuple(sorted(spec.get('files', {}).items())))

    def applies_to(self, platform: Platform) -> bool:
        """Whether this component goes into the platform's bundle (deb: only where listed)."""
        return self.kind != 'deb' or platform.name in self.raw['assets']

    def all_assets(self) -> list[Asset]:
        """Every asset of an archive or deb component, one per platform key (or "any")."""
        return [self._asset(spec) for spec in self.raw.get('assets', {}).values() if 'same_as' not in spec]

    def exe(self, platform: Platform) -> str | None:
        """Main executable, relative to the bundle root."""
        exe = self.raw.get('exe')
        if exe is None:
            return None
        if isinstance(exe, dict):
            rel = exe['windows' if platform.windows else 'unix']
        else:
            rel = platform.exe(exe)
        return f'{self.dest}/{rel}' if rel != '.' else self.dest

    def path_dirs(self, platform: Platform) -> list[str]:
        """Directories this component adds to PATH, relative to the bundle root."""
        dirs = self.raw.get('path_windows' if platform.windows else 'path', self.raw.get('path', []))
        return [self.dest if d == '.' else f'{self.dest}/{d}' for d in dirs]

    @property
    def license_files(self) -> list[str]:
        return list(self.raw.get('license_files', []))


@dataclass(frozen=True)
class Manifest:
    platforms: tuple[str, ...]
    components: tuple[Component, ...]
    sha256: str
    patchelf: dict = field(default_factory=dict, repr=False, compare=False)

    def patchelf_asset(self, host: str) -> Asset:
        spec = self.patchelf.get('assets', {}).get(host)
        if spec is None:
            raise ManifestError(f'no patchelf for host {host}')
        return Asset(url=spec['url'], sha256=spec['sha256'])

    def component(self, name: str) -> Component:
        for c in self.components:
            if c.name == name:
                return c
        raise ManifestError(f'no component {name!r}')


def _rel_path_ok(value: object) -> bool:
    if not isinstance(value, str) or not value or value.startswith('/') or '\\' in value:
        return False
    return '..' not in PurePosixPath(value).parts


def _check_download(where: str, key: str, spec: dict) -> list[str]:
    errors = []
    if not str(spec.get('url', '')).startswith('https://'):
        errors.append(f'{where}/{key}: url must be https')
    if not SHA256_RE.fullmatch(str(spec.get('sha256', ''))):
        errors.append(f'{where}/{key}: sha256 missing or malformed')
    return errors


def validate(data: dict) -> list[str]:
    """Every problem with a parsed manifest, as human-readable strings."""
    errors: list[str] = []
    if data.get('schema') != 1:
        errors.append('schema must be 1')
    platforms = data.get('platforms')
    if not isinstance(platforms, list) or not platforms or set(platforms) - set(PLATFORMS):
        errors.append(f'platforms must be a non-empty subset of {sorted(PLATFORMS)}')
        platforms = []
    components = data.get('components')
    if not isinstance(components, list) or not components:
        return errors + ['components must be a non-empty list']

    patchelf = data.get('patchelf')
    if patchelf is not None:
        if not isinstance(patchelf, dict) or not patchelf.get('version') or not patchelf.get('assets'):
            errors.append('patchelf needs version and assets')
        else:
            for key, spec in patchelf['assets'].items():
                if key not in PLATFORMS:
                    errors.append(f'patchelf: unknown host {key}')
                errors += _check_download('patchelf', key, spec)

    names: set[str] = set()
    dests: dict[str, str] = {}
    for c in components:
        name = c.get('name', '?')
        where = f'component {name}'
        if name in names:
            errors.append(f'{where}: duplicate name')
        names.add(name)
        for key in ('kind', 'version', 'license', 'homepage'):
            if not isinstance(c.get(key), str) or not c.get(key):
                errors.append(f'{where}: missing {key}')
        if c.get('kind') not in KINDS:
            errors.append(f'{where}: kind must be one of {KINDS}')
        if not str(c.get('homepage', '')).startswith('https://'):
            errors.append(f'{where}: homepage must be https')
        kind = c.get('kind')
        if kind != 'pip':
            dest = c.get('dest')
            if not _rel_path_ok(dest):
                errors.append(f'{where}: dest must be a relative posix path')
            elif any((dest == d and not (kind == k == 'deb')) or dest.startswith(d + '/') or d.startswith(dest + '/')
                     for d, k in dests.items()):
                errors.append(f'{where}: dest {dest} overlaps another component')
            else:
                dests[dest] = kind
        check = c.get('check')
        if check is not None:
            if not isinstance(check, dict) or not isinstance(check.get('expect'), str) or not check['expect']:
                errors.append(f'{where}: check needs a non-empty expect')
            elif 'script' in check:
                script = check['script']
                if not _rel_path_ok(script) or not (REPO_ROOT / script).is_file():
                    errors.append(f'{where}: check script missing')
        if 'runpath' in c:
            if kind != 'archive' or 'exe' not in c:
                errors.append(f'{where}: runpath needs an archive component with exe')
            elif not isinstance(c['runpath'], str) or not c['runpath'].startswith('$ORIGIN'):
                errors.append(f'{where}: runpath must start with $ORIGIN')
            elif patchelf is None:
                errors.append(f'{where}: runpath needs a patchelf pin')
        if kind == 'deb':
            assets = c.get('assets')
            if not isinstance(assets, dict) or not assets:
                errors.append(f'{where}: assets missing')
                continue
            for key, spec in assets.items():
                if key not in LINUX_PLATFORMS:
                    errors.append(f'{where}: deb assets are for {LINUX_PLATFORMS}, not {key}')
                errors += _check_download(where, key, spec)
                files = spec.get('files')
                if not isinstance(files, dict) or not files:
                    errors.append(f'{where}/{key}: files missing')
                    continue
                for name, member in files.items():
                    if not SONAME_RE.fullmatch(name) or not _rel_path_ok(member):
                        errors.append(f'{where}/{key}: bad file {name} <- {member}')
        if kind == 'archive':
            assets = c.get('assets')
            if not isinstance(assets, dict) or not assets:
                errors.append(f'{where}: assets missing')
                continue
            if 'any' not in assets:
                for p in platforms:
                    if p not in assets:
                        errors.append(f'{where}: no asset for {p}')
            for key, spec in assets.items():
                if key != 'any' and key not in PLATFORMS:
                    errors.append(f'{where}: unknown platform {key}')
                if 'same_as' in spec:
                    target = assets.get(spec['same_as'])
                    if len(spec) != 1 or target is None or 'same_as' in target:
                        errors.append(f'{where}/{key}: same_as must be the only field and name '
                                      'another platform\'s asset')
                    continue
                errors += _check_download(where, key, spec)
                exclude = spec.get('exclude', [])
                if not isinstance(exclude, list) or not all(isinstance(e, str) and e for e in exclude):
                    errors.append(f'{where}/{key}: exclude must be a list of patterns')
                root = spec.get('root', c.get('root'))
                if root not in (None, '') and not _rel_path_ok(root):
                    errors.append(f'{where}/{key}: root must be a relative posix path')
        elif kind == 'git':
            if not str(c.get('url', '')).startswith('https://'):
                errors.append(f'{where}: url must be https')
            if not COMMIT_RE.fullmatch(str(c.get('commit', ''))):
                errors.append(f'{where}: commit must be a full sha1')
            for path, commit in (c.get('submodules') or {}).items():
                if not _rel_path_ok(path) or not COMMIT_RE.fullmatch(str(commit)):
                    errors.append(f'{where}: bad submodule pin {path}')
            for path, files in (c.get('keep') or {}).items():
                if path not in (c.get('submodules') or {}):
                    errors.append(f'{where}: keep names {path}, which is not a pinned submodule')
                if not isinstance(files, list) or not files or not all(_rel_path_ok(f) for f in files):
                    errors.append(f'{where}: keep {path} must be a non-empty list of relative paths')
        elif kind == 'pip':
            if c.get('interpreter') not in names:
                errors.append(f'{where}: interpreter must name an earlier component')
            req = c.get('requirements')
            if not _rel_path_ok(req) or not (REPO_ROOT / req).is_file():
                errors.append(f'{where}: requirements file missing')
    return errors


def load(path: Path = MANIFEST) -> Manifest:
    raw_bytes = path.read_bytes()
    data = json.loads(raw_bytes)
    errors = validate(data)
    if errors:
        raise ManifestError('invalid manifest:\n  ' + '\n  '.join(errors))
    components = tuple(
        Component(
            name=c['name'], kind=c['kind'], version=c['version'], license=c['license'],
            homepage=c['homepage'], dest=c.get('dest', ''), raw=c,
        )
        for c in data['components']
    )
    return Manifest(tuple(data['platforms']), components, hashlib.sha256(raw_bytes).hexdigest(),
                    data.get('patchelf', {}))
