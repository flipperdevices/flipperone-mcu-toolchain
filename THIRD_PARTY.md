# Third-party components

A bundle redistributes the upstream binaries below. The only change: on Linux, picotool
and the libraries in `tools/lib` get a RUNPATH (patchelf) that points them at
`tools/lib`. Exact versions,
download URLs and sha256 hashes for each platform are in the bundle's `toolchain.json`.
License texts that ship inside an upstream archive stay in the bundle:
- **xPack tools (GCC, CMake, Ninja):** under `tools/<component>/distro-info/licenses/`.
- **Python:** in the interpreter tree. Each installed package keeps its licence in its
  `*.dist-info` directory.
- **Everything else:** copied to `licenses/<component>/`.

| Component | Version | License | Corresponding source |
|---|---|---|---|
| xPack GNU Arm Embedded GCC (GCC, binutils, newlib, GDB) | 14.2.1-1.1 | GPL-3.0-or-later WITH GCC-exception-3.1, LGPL, newlib licenses | <https://github.com/xpack-dev-tools/arm-none-eabi-gcc-xpack/releases/tag/v14.2.1-1.1>, which links the Arm 14.2.Rel1 sources it builds |
| Raspberry Pi Pico SDK, with TinyUSB, without BTstack | 2.3.1 | BSD-3-Clause; TinyUSB MIT | <https://github.com/raspberrypi/pico-sdk/tree/2.3.1> (included in the bundle as source) |
| picotool | 2.3.1 | BSD-3-Clause | <https://github.com/raspberrypi/picotool/tree/2.3.1> |
| pioasm | 2.3.1 | BSD-3-Clause | <https://github.com/raspberrypi/pico-sdk/tree/2.3.1/tools/pioasm> |
| OpenOCD, Flipper build (mainline plus patches; libusb, hidapi, libftdi1, jimtcl and libjaylink linked statically, their licenses in `tools/openocd/licenses/`) | 0.12.0+dev-flipper-v1 | GPL-2.0-or-later | <https://github.com/flipperdevices/openocd/releases/tag/flipper-v1> |
| libusb (Linux bundles, Debian package `libusb-1.0-0`) | 1.0.26-1 | LGPL-2.1-or-later | <https://snapshot.debian.org/package/libusb-1.0/2:1.0.26-1/> |
| libftdi1 (Linux bundles, Debian package `libftdi1-2`) | 1.5-6 | LGPL-2.1-only | <https://snapshot.debian.org/package/libftdi1/1.5-6/> |
| hidapi (Linux bundles, Debian package `libhidapi-hidraw0`) | 0.13.1-1 | GPL-3.0-only OR BSD-3-Clause OR HIDAPI license; redistributed under BSD-3-Clause | <https://snapshot.debian.org/package/hidapi/0.13.1-1/> |
| xPack CMake | 3.31.9-1 | BSD-3-Clause | <https://github.com/xpack-dev-tools/cmake-xpack/releases/tag/v3.31.9-1> |
| xPack Ninja | 1.13.1-1 | Apache-2.0 | <https://github.com/xpack-dev-tools/ninja-build-xpack/releases/tag/v1.13.1-1> |
| CPython (python-build-standalone) | 3.12.16 (20261026) | PSF-2.0 and the licenses of its bundled libraries | <https://github.com/astral-sh/python-build-standalone/releases/tag/20261026> |
| Python packages: the ones in `python/requirements-build.in` and their dependencies | see `python/requirements.lock` | MIT (ansi, black, cffi, charset-normalizer, mypy-extensions, oslex, platformdirs, pytokens, scons, setuptools, urllib3), BSD-3-Clause (click, idna, protobuf, pycparser, pyserial), BSD-2-Clause (crc), Apache-2.0 (dataclass-wizard, grpcio, grpcio-tools, mslex, requests), Apache-2.0 OR BSD-2-Clause (packaging), Apache-2.0 OR BSD-3-Clause (cryptography; its wheels include OpenSSL, Apache-2.0), MPL-2.0 (certifi, pathspec), HPND (pillow), PSF-2.0 (typing-extensions) | PyPI; each package's licence ships in its `*.dist-info` directory in the bundled interpreter |
| uv | 0.13.7 | MIT OR Apache-2.0 | <https://github.com/astral-sh/uv/tree/0.13.7> |
| ccache | 4.14.3 | GPL-3.0-or-later | <https://github.com/ccache/ccache/releases/tag/v4.14.3> |
| clang-format, clang-tidy, clangd (LLVM, PyPI wheels) | 22.1.1, 22.1.0.1 (LLVM 22.1.0), 22.1.1 | Apache-2.0 WITH LLVM-exception | <https://github.com/llvm/llvm-project>; wheels from <https://github.com/ssciwr/clang-format-wheel>, <https://github.com/ssciwr/clang-tidy-wheel> and <https://github.com/jmpfar/clangd-wheel> |

The scripts that assemble the bundle are MIT-licensed; see `licenses/LICENSE`.

GPL and LGPL components are distributed in binary form as published by their upstream
projects, apart from the RUNPATH entries above; the sources are unchanged. The links above
point to the corresponding sources for the exact versions.
