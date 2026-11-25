# Flipper One MCU toolchain

Everything needed to build, flash, debug and lint Flipper One MCU (RP2350) firmware in
one versioned, hash-verified bundle. It ships as an archive for each platform and as a
Docker image.

| Platform | Archive |
|---|---|
| Linux x86_64 | `flipperone-mcu-toolchain-<tag>-linux-x86_64.tar.gz` |
| Linux aarch64 | `flipperone-mcu-toolchain-<tag>-linux-aarch64.tar.gz` |
| macOS arm64 | `flipperone-mcu-toolchain-<tag>-darwin-arm64.tar.gz` |
| Windows x64 | `flipperone-mcu-toolchain-<tag>-windows-x64.zip` |

The bundle contains:
- Arm GCC 14.2.1 (xPack), with GDB (built without Python scripting)
- Pico SDK 2.3.1, with its TinyUSB submodule and without BTstack (see below)
- picotool and pioasm 2.3.1, prebuilt
- OpenOCD (the Raspberry Pi fork)
- CMake and Ninja
- Python 3.12, with build packages already installed: pillow, protobuf, and grpcio-tools
  (bundles protoc)
- uv and ccache
- clang-format and clang-tidy

[`manifest.json`](manifest.json) pins every component by URL and sha256, and
[THIRD_PARTY.md](THIRD_PARTY.md) lists their licenses.

## Using a bundle

Unpack the archive anywhere; the bundle has no absolute paths baked in. Then load its
environment.

```shell
# bash or zsh
. /path/to/bundle/fbtenv.sh
```

```powershell
# PowerShell
. C:\path\to\bundle\fbtenv.ps1
```

```bat
rem cmd.exe
call C:\path\to\bundle\fbtenv.cmd
```

The scripts put the tools first on `PATH` and set these variables:

| Variable | Value |
|---|---|
| `FLIPPERONE_TOOLCHAIN` | the bundle's tag |
| `FLIPPERONE_TOOLCHAIN_ROOT` | the bundle's root directory |
| `PICO_SDK_PATH`, `PICO_TOOLCHAIN_PATH` | the SDK and the compiler, for the SDK's CMake |
| `picotool_DIR`, `pioasm_DIR` | the prebuilt tools, so the SDK does not build them from source |
| `OPENOCD_SCRIPTS` | OpenOCD's scripts directory |
| `PYTHONNOUSERSITE` | `1`, which keeps user site-packages out of the bundled Python |

Sourcing a script again, or sourcing another bundle's script, replaces the earlier
`PATH` entries instead of adding to them.

For IDEs and shells that cannot load an env script, pass the initial-cache file to CMake:

```shell
cmake -C /path/to/bundle/cmake/initial-cache.cmake -G Ninja -S . -B build
```

This sets the same paths, plus `Python3_EXECUTABLE`, as cache entries. Do not pass it
as `CMAKE_TOOLCHAIN_FILE`: the Pico SDK needs `PICO_SDK_PATH` before `project()`, and
chooses its own toolchain file.

### Host requirements

- **Linux:** glibc 2.34 or newer, for example Ubuntu 22.04 or Debian 12, and `libudev1`,
  which every systemd-based distribution has. picotool and OpenOCD use the libusb,
  libftdi1, hidapi (and on aarch64 libgpiod) in `tools/lib`, not the system's. To use a debug probe or a BOOTSEL
  device without root, install udev rules for them once, e.g. picotool's
  [`60-picotool.rules`](https://github.com/raspberrypi/picotool/blob/master/udev/60-picotool.rules)
  and OpenOCD's `contrib/60-openocd.rules`, into `/etc/udev/rules.d/`.
- **macOS:** an archive downloaded with a browser is quarantined. Clear the flag before
  use with `xattr -dr com.apple.quarantine <bundle>`.
- **Windows:** keep the bundle path short, for example under `%LOCALAPPDATA%`.
  - Loading BOOTSEL devices with picotool needs the WinUSB driver (use Zadig).
  - OpenOCD over CMSIS-DAP needs no driver.
  - If PowerShell blocks scripts, run
    `powershell -ExecutionPolicy Bypass -NoExit -File <bundle>\fbtenv.ps1`.

### Docker image

`docker/Dockerfile` builds the Linux bundle into a pinned Debian image. The bundle goes
in `/opt/flipperone-mcu-toolchain`, the environment above is set through `ENV`, and the
image runs as the non-root user `builder`, uid 1000. In a GitHub Actions `container:` job,
add `options: --user root` so that the job can write to the workspace the runner mounts.

## Releases

A release is tagged `v<N>`, with N counting up; component versions are in the release,
not in the tag. Each GitHub release has:

- the four archives
- `SHA256SUMS`, covering the archives
- `release.json`: the machine-readable description, for tools that pin or update a
  toolchain. It has `tag`, `source_commit`, `archives` (per platform: `name`, `sha256`,
  `size`), `image` (`name`, `digest`), and `components` (`version`, `license`, and
  `commit` for git components).

The image is `ghcr.io/flipperdevices/flipperone-mcu-toolchain:v<N>`, for linux/amd64 and
linux/arm64. Pin it by the digest in `release.json`, not by tag.

Once the repository is public, each release also carries build provenance for the
archives and the image. Check it with:
- `gh attestation verify <archive> -R flipperdevices/flipperone-mcu-toolchain`
- `gh attestation verify oci://ghcr.io/flipperdevices/flipperone-mcu-toolchain@<digest> -R flipperdevices/flipperone-mcu-toolchain`

## Bundle contents

```
toolchain.json            tag, platform, source commit and every component's version, URL and hash
SHA256SUMS                hash of every file in the bundle
fbtenv.sh | fbtenv.ps1, fbtenv.cmd
cmake/initial-cache.cmake
pico-sdk/
tools/<component>/        arm-none-eabi-gcc, picotool, pioasm, openocd, cmake, ninja,
                          python, uv, ccache, clang-format, clang-tidy
tools/lib/                Linux only: libusb, libftdi1, hidapi (and libgpiod) for picotool and OpenOCD
licenses/  THIRD_PARTY.md
```

`pico-sdk/lib/btstack` is empty: BTstack's license allows only non-commercial use outside
Raspberry Pi's own wireless boards, and nothing the bundle builds needs it. The SDK then
defines none of its `pico_btstack_*` targets.

The layout, the variable names and the `toolchain.json` schema are a public contract.
Changing any of them is a breaking change; see [CONTRIBUTING.md](CONTRIBUTING.md).

## Building a bundle

The assembler needs only Python 3.12 or newer, with no packages.

```shell
python3 -m assembler --platform darwin-arm64 --out dist   # --platform defaults to this host
```

It downloads each component into a cache (`~/.cache/flipperone-mcu-toolchain`) and checks
the sha256 pinned in the manifest. It then lays out the bundle and writes `toolchain.json`,
`SHA256SUMS` and the env scripts, and packs `dist/flipperone-mcu-toolchain-<tag>-<platform>.*`
together with a `.sha256` file.

- **Determinism:** archives are deterministic. The same commit always gives the same bytes:
  entries are sorted, each mtime is `SOURCE_DATE_EPOCH` (by default the commit time), and
  ownership and modes are normalised.
- **Offline:** `--offline` builds from the cache alone.
- **Mirror:** with `--mirror owner/repo@tag` (or `FLIPPERONE_TOOLCHAIN_MIRROR`), a failed or
  changed upstream download is retried from that release. The weekly Upstream workflow
  keeps a copy of every pinned archive in this repository's `mirror` release, so old tags
  stay buildable. The Pico SDK, from git, and the PyPI packages are not mirrored.
- **Native host only:** the Python packages install with the bundled interpreter, so a
  bundle must be assembled on its own platform.

To test an unpacked bundle, load its env and run the smoke test:

```shell
. dist/<bundle>/fbtenv.sh && python3 tests/smoke/run.py
```

The smoke test checks:
- the files against `SHA256SUMS`
- every variable and `PATH` entry
- every tool's version
- a small RP2350 project (`tests/smoke/blink`), built once with the env and once with
  only the initial cache

The smoke test prints the project's `blink.uf2` hash, so builds on different platforms can
be compared.
