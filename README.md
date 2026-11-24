# Flipper One MCU toolchain

Everything needed to build, flash, debug and lint the
[Flipper One MCU firmware](https://github.com/flipperdevices/flipperone-mcu-firmware) in
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
- Pico SDK 2.3.1, with its TinyUSB submodule and three files of BTstack (see below)
- picotool and pioasm 2.3.1, prebuilt
- OpenOCD (the Raspberry Pi fork)
- CMake and Ninja
- Python 3.12, with the firmware's build packages already installed
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
| `OPENOCD_SCRIPTS`, `F1_OPENOCD` | OpenOCD's scripts and binary; the firmware's `swd.py` reads `F1_OPENOCD` |
| `ARM_TOOLCHAIN_BIN` | the compiler's `bin/`; the firmware's `isr_ram_check.py` reads it |
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

- **Linux:** glibc 2.34 or newer, for example Ubuntu 22.04 or Debian 12. The Raspberry Pi
  picotool and OpenOCD builds also need these system libraries:
  `apt install libusb-1.0-0 libftdi1-2 libhidapi-hidraw0`
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

## Bundle contents

```
toolchain.json            tag, platform, source commit and every component's version, URL and hash
SHA256SUMS                hash of every file in the bundle
fbtenv.sh | fbtenv.ps1, fbtenv.cmd
cmake/initial-cache.cmake
pico-sdk/
tools/<component>/        arm-none-eabi-gcc, picotool, pioasm, openocd, cmake, ninja,
                          python, uv, ccache, clang-format, clang-tidy
licenses/  THIRD_PARTY.md
```

`pico-sdk/lib/btstack` holds only three files:
- `platform/embedded/hal_flash_bank.h`, which the firmware's kvstore needs through the
  SDK's `pico/btstack_flash_bank.h`. It is BSD-3-Clause.
- `src/bluetooth.h`, which the SDK only checks for, to define its `pico_btstack_*`
  targets at all.
- `LICENSE`.

The SDK's other BTstack targets are not usable with this bundle.

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
- **Native host only:** the Python packages install with the bundled interpreter, so a
  bundle must be assembled on its own platform.

To test an unpacked bundle, load its env and run the smoke test:

```shell
. dist/<bundle>/fbtenv.sh && python3 tests/smoke/run.py \
    [--firmware ../flipperone-mcu-firmware --target f2 --target f1]
```

The smoke test checks:
- the files against `SHA256SUMS`
- every variable and `PATH` entry
- every tool's version
- a small RP2350 project, built once with the env and once with only the initial cache

With `--firmware`, it also builds the firmware.
