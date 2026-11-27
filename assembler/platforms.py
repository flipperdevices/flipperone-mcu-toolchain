"""Bundle platforms: names, archive formats and host detection."""

from __future__ import annotations

import platform
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class Platform:
    name: str
    os: str  # "linux", "darwin" or "windows"
    archive: str  # "tar.gz" or "zip"

    @property
    def windows(self) -> bool:
        return self.os == 'windows'

    def exe(self, path: str) -> str:
        """Executable path for this platform: appends .exe on Windows."""
        return path + '.exe' if self.windows and not path.endswith('.exe') else path


PLATFORMS = {
    p.name: p
    for p in (
        Platform('linux-x86_64', 'linux', 'tar.gz'),
        Platform('linux-aarch64', 'linux', 'tar.gz'),
        Platform('darwin-arm64', 'darwin', 'tar.gz'),
        Platform('windows-x64', 'windows', 'zip'),
        Platform('windows-arm64', 'windows', 'zip'),
    )
}


def archive_name(tag: str, platform_name: str) -> str:
    """File name of a bundle archive."""
    return f'flipperone-mcu-toolchain-{tag}-{platform_name}.{PLATFORMS[platform_name].archive}'


def host_platform() -> str | None:
    """The bundle platform this interpreter runs on, or None if unsupported."""
    machine = platform.machine().lower()
    if sys.platform.startswith('linux'):
        return {'x86_64': 'linux-x86_64', 'amd64': 'linux-x86_64',
                'aarch64': 'linux-aarch64', 'arm64': 'linux-aarch64'}.get(machine)
    if sys.platform == 'darwin':
        return 'darwin-arm64' if machine == 'arm64' else None
    if sys.platform == 'win32':
        # An x64 Python on Windows on Arm reports AMD64: run an arm64 one to assemble for arm64
        return {'amd64': 'windows-x64', 'x86_64': 'windows-x64',
                'arm64': 'windows-arm64', 'aarch64': 'windows-arm64'}.get(machine)
    return None
