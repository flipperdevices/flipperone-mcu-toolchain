# Building a bundle

The assembler needs only Python 3.12 or newer, with no packages:

```shell
python3 -m assembler --platform darwin-arm64 --out dist   # --platform defaults to this host
```

It downloads each component into a cache (`~/.cache/flipperone-mcu-toolchain`), checks the sha256 pinned in `manifest.json`, lays out the bundle, writes `toolchain.json`, `SHA256SUMS` and the env scripts, and packs `dist/flipperone-mcu-toolchain-<tag>-<platform>.*` with a `.sha256` file.

- **Native host only:** the Python packages install with the bundled interpreter, so a bundle is assembled on its own platform. For windows-arm64, run the assembler with an arm64 Python.
- **Deterministic:** the same commit gives the same bytes. Entries are sorted, every mtime is `SOURCE_DATE_EPOCH` (by default the commit time), and ownership and modes are normalised.
- **Offline:** `--offline` builds from the cache alone.
- **Mirror:** with `--mirror owner/repo@tag` (or `FLIPPERONE_TOOLCHAIN_MIRROR`), a failed or changed upstream download is retried from that release. The weekly Upstream workflow keeps every pinned archive in this repository's `mirror` release, so old tags stay buildable. The Pico SDK (git) and the PyPI packages are not mirrored.

## Smoke test

Load an unpacked bundle's environment and run:

```shell
. dist/<bundle>/fbtenv.sh && python3 tests/smoke/run.py
```

It checks:
- the files against `SHA256SUMS`, and the bundle's manifest hash against this checkout
- every variable and `PATH` entry, and every tool's version
- on Linux, that every tool finds its libraries; on Windows, Microsoft's signature on the bundled runtime DLLs
- a small RP2350 project (`tests/smoke/blink`), built once with the env and once with only the initial cache, and parsed by clangd

It prints the project's `blink.uf2` hash, so builds on different platforms can be compared.
