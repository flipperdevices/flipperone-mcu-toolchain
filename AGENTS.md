# AGENTS.md

Orientation for AI agents in this repository. [README.md](README.md) and
[CONTRIBUTING.md](CONTRIBUTING.md) own the details.

## What this is

The assembler for the Flipper One MCU toolchain bundle: upstream prebuilt tools, pinned by
URL and sha256 in `manifest.json`, repacked into one relocatable archive per platform and a
Docker image.

## Layout

| Path | Contents |
| --- | --- |
| `manifest.json` | Every component: kind (archive, git, pip or deb), version, license, `dest`, per-platform URL and sha256, and the version check; the pinned patchelf |
| `assembler/` | Stdlib-only Python 3.12. `__main__` assembles; `pin` fills and checks hashes; `env` defines the runtime contract and renders the env scripts; `release` writes `SHA256SUMS`, `release.json` and the notes; `mirror` fills the `mirror` release |
| `python/` | The bundle's Python packages and their hashed universal lock; `README.md` there says how to change them |
| `docs/dependencies.md` | How to update a component, and the `manifest.json` reference |
| `docker/Dockerfile` | The image built from the Linux bundles |
| `.github/workflows/` | `build.yml` (PRs, `dev`, and called by the release), `release.yml` (tags `v<N>`), `upstream.yml` (weekly pin check and mirror) |
| `tests/` | Host unit tests; `smoke/run.py` tests a real unpacked bundle by building the RP2350 project in `smoke/blink` |

## Rules that are easy to get wrong

- Never edit a sha256 by hand: blank it and run `python3 -m assembler.pin --write`.
- The variable names, the bundle layout and the `toolchain.json` schema are a public
  contract (see CONTRIBUTING.md). The Dockerfile's `ENV` must match `assembler/env.py`;
  `tests/test_env.py` checks it.
- A bundle must be assembled on its own platform, because the pip component runs the
  bundled interpreter.
- Use only upstream releases that are at least two weeks old.
- The default branch is `dev`.

## Checks

```shell
.venv/bin/ruff check . && .venv/bin/python -m pytest -q
```
