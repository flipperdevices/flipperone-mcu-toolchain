# Flipper One MCU toolchain

Everything needed to build, flash, debug and lint Flipper One MCU (RP2350) firmware, in one versioned, hash-verified bundle per platform.

| Platform | Archive |
|---|---|
| Linux x86_64 | `flipperone-mcu-toolchain-<tag>-linux-x86_64.tar.gz` |
| Linux aarch64 | `flipperone-mcu-toolchain-<tag>-linux-aarch64.tar.gz` |
| macOS arm64 | `flipperone-mcu-toolchain-<tag>-darwin-arm64.tar.gz` |
| Windows x64 | `flipperone-mcu-toolchain-<tag>-windows-x64.zip` |
| Windows on Arm | `flipperone-mcu-toolchain-<tag>-windows-arm64.zip` |

Download them from the [releases](https://github.com/flipperdevices/flipperone-mcu-toolchain/releases). A Docker image is built too: [docs/usage.md](docs/usage.md#docker-image).

## Contents

- Arm GCC 14.2.1 (xPack), with GDB
- Pico SDK 2.3.1, with TinyUSB and without BTstack
- picotool and pioasm 2.3.1
- OpenOCD, [Flipper's build](https://github.com/flipperdevices/openocd): mainline plus FreeRTOS thread support on Cortex-M33
- CMake, Ninja, ccache, uv
- Python 3.12 with the firmware's build packages ([python/README.md](python/README.md))
- clangd, clang-format and clang-tidy (LLVM 22)

[`manifest.json`](manifest.json) pins every component by URL and sha256; [THIRD_PARTY.md](THIRD_PARTY.md) lists versions and licenses.

## Use

Unpack anywhere, then load the environment:

```shell
. /path/to/bundle/fbtenv.sh                 # bash, zsh
. C:\path\to\bundle\fbtenv.ps1              # PowerShell
call C:\path\to\bundle\fbtenv.cmd           # cmd.exe
```

The tools come first on `PATH`, and `PICO_SDK_PATH`, `PICO_TOOLCHAIN_PATH`, `picotool_DIR`, `pioasm_DIR` and `OPENOCD_SCRIPTS` point into the bundle. Without an env script, for example in an IDE:

```shell
cmake -C /path/to/bundle/cmake/initial-cache.cmake -G Ninja -S . -B build
```

All variables, Windows details and the Docker image: [docs/usage.md](docs/usage.md).

## Host requirements

- **Linux:** glibc 2.34 or newer (Ubuntu 22.04, Debian 12) and `libudev1`. Install udev rules to use probes without root: [docs/usage.md](docs/usage.md#linux).
- **macOS:** Apple silicon. Clear the browser quarantine flag: `xattr -dr com.apple.quarantine <bundle>`.
- **Windows:** x64 or Arm. No drivers or redistributables for OpenOCD and the clang tools; picotool needs WinUSB for BOOTSEL devices. Keep the bundle path short.

## More

| Document | Covers |
|---|---|
| [docs/usage.md](docs/usage.md) | Environment variables, CMake initial cache, platform notes, Docker image |
| [docs/releases.md](docs/releases.md) | Release assets, `release.json`, image, provenance, bundle layout |
| [docs/building.md](docs/building.md) | Assembling a bundle, determinism, mirror, smoke test |
| [docs/dependencies.md](docs/dependencies.md) | Updating components; the manifest format |
| [python/README.md](python/README.md) | Adding and updating Python packages |
| [CONTRIBUTING.md](CONTRIBUTING.md) | CI, releasing, the public contract |
