# Releases and the bundle layout

## Releases

A release is tagged `v<N>`, N counting up; component versions are in the release, not in the tag. Each GitHub release has:

- the five archives
- `SHA256SUMS`, covering the archives
- `release.json`, the machine-readable description for tools that pin or update a toolchain: `tag`, `source_commit`, `archives` (per platform: `name`, `sha256`, `size`), `image` (`name`, `digest`) and `components` (`version`, `license`, `commit` for git components, `platforms` for components on some platforms only)

The image is `ghcr.io/flipperdevices/flipperone-mcu-toolchain:v<N>`, for linux/amd64 and linux/arm64. Pin it by the digest in `release.json`, not by tag.

Each release carries build provenance for the archives and the image:

```shell
gh attestation verify <archive> -R flipperdevices/flipperone-mcu-toolchain
gh attestation verify oci://ghcr.io/flipperdevices/flipperone-mcu-toolchain@<digest> -R flipperdevices/flipperone-mcu-toolchain
```

How to cut a release: [CONTRIBUTING.md](../CONTRIBUTING.md).

## Bundle layout

```
toolchain.json            tag, platform, source commit, every component's version, URL and hash
SHA256SUMS                hash of every file in the bundle
fbtenv.sh | fbtenv.ps1, fbtenv.cmd
cmake/initial-cache.cmake
pico-sdk/
tools/<component>/        arm-none-eabi-gcc, picotool, pioasm, openocd, cmake, ninja,
                          python, uv, ccache, clang-format, clang-tidy, clangd
tools/lib/                Linux only: libusb, libftdi1, hidapi for picotool
licenses/  THIRD_PARTY.md
```

`pico-sdk/lib/btstack` is empty: BTstack's license allows only non-commercial use outside Raspberry Pi's own wireless boards, and nothing the bundle builds needs it. The SDK then defines none of its `pico_btstack_*` targets.

The layout, the [environment variables](usage.md#environment) and the `toolchain.json` schema are a public contract: changing any of them is a breaking change ([CONTRIBUTING.md](../CONTRIBUTING.md)).
