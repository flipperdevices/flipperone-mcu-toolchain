# Contributing

Branch from `dev` and open a pull request against it. CI does the following:
- assembles all four platforms on their native runners and smoke-tests each bundle
- smoke-tests both Linux bundles on the oldest supported glibc, without the system USB
  libraries the bundle ships
- builds the Docker image for both architectures
- smoke-tests the Docker image as its non-root user, using only the image's `ENV`

## Updating dependencies

- Python packages: [python/README.md](python/README.md).
- Everything else, and the `manifest.json` reference: [docs/dependencies.md](docs/dependencies.md).

A project that needs a changed dependency needs a toolchain release first.

## Releasing

1. Make sure CI is green on the `dev` commit to release.
2. Tag it with the next `v<N>` and push the tag:

   ```shell
   git tag v<N> <commit> && git push origin v<N>
   ```

3. The Release workflow then:
   - checks that the tag is `v<N>` on a `dev` commit
   - rebuilds and tests every platform from the tag (it reuses `build.yml`)
   - pushes the image
   - creates the GitHub release with the archives, `SHA256SUMS` and `release.json`
   - attests the archives and the image, if the repository is public

Consumers pick up new releases by reading `release.json`. This repository never opens
pull requests anywhere else.

## Upstream changes

The weekly Upstream workflow, which can also be run by hand, does two things:
- runs `python3 -m assembler.pin`. It fails if any pinned upstream file has changed or
  disappeared.
- runs `python3 -m assembler.mirror`. It uploads every pinned archive that is not yet in
  the `mirror` release, as `<sha256>-<file name>`. Mirror assets are never deleted,
  because old tags may need them.

## The bundle contract

These are a public contract that projects and developers' setups depend on:
- the bundle layout (`pico-sdk/`, `tools/<component>/`, `cmake/initial-cache.cmake`, the
  `fbtenv.*` scripts)
- the variable names in `assembler/env.py`
- the `toolchain.json` schema

Changing any of them is a breaking change. It needs a new major tag, and consumers must
be updated to handle both bundles.

`docker/Dockerfile` repeats the environment in its `ENV` block. `tests/test_env.py` fails
if the two disagree.

## Checks

```shell
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/ruff check . && .venv/bin/python -m pytest -q
```
