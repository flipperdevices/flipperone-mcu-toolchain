# Using a bundle

## Environment

Unpack the archive anywhere; the bundle has no absolute paths baked in. `fbtenv.sh` (bash, zsh), `fbtenv.ps1` (PowerShell) and `fbtenv.cmd` (cmd.exe) put the tools first on `PATH` and set:

| Variable | Value |
|---|---|
| `FLIPPERONE_TOOLCHAIN` | the bundle's tag |
| `FLIPPERONE_TOOLCHAIN_ROOT` | the bundle's root directory |
| `PICO_SDK_PATH`, `PICO_TOOLCHAIN_PATH` | the SDK and the compiler, for the SDK's CMake |
| `picotool_DIR`, `pioasm_DIR` | the prebuilt tools, so the SDK does not build them from source |
| `OPENOCD_SCRIPTS` | OpenOCD's scripts directory |
| `PYTHONNOUSERSITE` | `1`: keeps user site-packages out of the bundled Python |

Sourcing a script again, or another bundle's script, replaces the earlier `PATH` entries instead of adding to them.

## CMake initial cache

For IDEs and shells that cannot load an env script:

```shell
cmake -C /path/to/bundle/cmake/initial-cache.cmake -G Ninja -S . -B build
```

It sets the same paths, plus `Python3_EXECUTABLE`, as cache entries. Do not pass it as `CMAKE_TOOLCHAIN_FILE`: the Pico SDK needs `PICO_SDK_PATH` before `project()` and chooses its own toolchain file.

## Platform notes

### Linux

- Needs glibc 2.34 or newer and `libudev1`, which every systemd-based distribution has.
- picotool uses the libusb, libftdi1 and hidapi in `tools/lib`, not the system's; OpenOCD has them linked in.
- To use a debug probe or a BOOTSEL device without root, install udev rules once into `/etc/udev/rules.d/`: picotool's [`60-picotool.rules`](https://github.com/raspberrypi/picotool/blob/master/udev/60-picotool.rules) and OpenOCD's `tools/openocd/contrib/60-openocd.rules`.

### macOS

An archive downloaded with a browser is quarantined. Clear the flag before use: `xattr -dr com.apple.quarantine <bundle>`.

### Windows

- Keep the bundle path short, for example under `%LOCALAPPDATA%`.
- OpenOCD over CMSIS-DAP needs no driver. picotool needs the WinUSB driver (Zadig) for BOOTSEL devices.
- No Visual C++ Redistributable is needed: the clang tools carry the Microsoft C++ runtime DLLs next to them.
- If PowerShell blocks scripts: `powershell -ExecutionPolicy Bypass -NoExit -File <bundle>\fbtenv.ps1`.
- **Windows on Arm:** OpenOCD, CMake, uv, ccache, clangd and clang-format are native arm64. Arm GCC, picotool, pioasm, Ninja, clang-tidy and Python with its packages are x64 builds, which Windows runs by emulation: upstream ships no arm64 build of them, or of some of the Python packages.

## Docker image

`docker/Dockerfile` builds the Linux bundle into a pinned Debian image. The bundle is in `/opt/flipperone-mcu-toolchain`, the environment above is set through `ENV`, and the image runs as the non-root user `builder` (uid 1000). In a GitHub Actions `container:` job, add `options: --user root` so the job can write to the workspace the runner mounts.

The image is `ghcr.io/flipperdevices/flipperone-mcu-toolchain:v<N>`; pin it by digest ([releases.md](releases.md)).
