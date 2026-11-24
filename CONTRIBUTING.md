# Contributing

Branch from `dev` and open a pull request against it. CI does the following:
- assembles all four platforms on their native runners and smoke-tests each bundle
- smoke-tests the Linux x86_64 bundle on the oldest supported glibc
- builds the Docker image for both architectures
- builds the firmware's f2 and f1 targets with every bundle

## Bumping a component

1. Edit the component in `manifest.json`: `version`, the asset URLs, any `root` or
   `license_files` that changed, and the `check.expect` string.
2. Clear the old hashes (`"sha256": ""`; for the Pico SDK, `"commit": ""`), then fill them
   from upstream metadata:

   ```shell
   GITHUB_TOKEN=$(gh auth token) python3 -m assembler.pin --write
   python3 -m assembler.pin    # every line must say ok
   ```

   `assembler.pin` reads, in this order of preference:
   - the digest GitHub records for each release asset
   - xPack's `.sha` files
   - PyPI's digests
   - `git ls-remote`

   If an asset has none of these, it hashes a download, and says so.
3. Update the versions in `THIRD_PARTY.md` and `README.md`.
   - If you bump the Pico SDK, re-check its `keep` list for `lib/btstack`. Build the
     firmware, then list the BTstack headers it actually used:
     `ninja -t deps | grep lib/btstack`.
   - A file in the list that is missing fails the assembly.
4. Assemble and smoke-test locally on at least one platform. If the compiler, SDK,
   picotool or Python packages changed, also build the firmware.

Use only releases that are at least two weeks old.

## Python build packages

`python/requirements-build.in` holds the firmware's build-time Python dependencies.
`python/requirements.lock` pins them, with hashes for every platform.

**A firmware change to these dependencies needs a toolchain release first.** Change the
`.in` file, then regenerate the lock:

```shell
uv pip compile python/requirements-build.in --universal --python-version 3.12 \
  --generate-hashes --exclude-newer <date two weeks ago> -o python/requirements.lock
```

## The bundle contract

These are a public contract that the firmware repo and developers' setups depend on:
- the bundle layout (`pico-sdk/`, `tools/<component>/`, `cmake/initial-cache.cmake`, the
  `fbtenv.*` scripts)
- the variable names in `assembler/env.py`
- the `toolchain.json` schema

Changing any of them is a breaking change. It needs a new major tag and a matching
firmware PR that can handle both bundles.

`docker/Dockerfile` repeats the environment in its `ENV` block. `tests/test_env.py` fails
if the two disagree.

## Checks

```shell
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/ruff check . && .venv/bin/python -m pytest -q
```
