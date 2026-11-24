# Contributing

Branch from `dev` and open a pull request against it. CI does the following:
- assembles all four platforms on their native runners and smoke-tests each bundle
- smoke-tests the Linux x86_64 bundle on the oldest supported glibc
- builds the Docker image for both architectures
- smoke-tests the Docker image as its non-root user, using only the image's `ENV`

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
   - If you bump the Pico SDK, re-check its `keep` list for `lib/btstack`: the files
     `pico_btstack_flash_bank_headers` needs. The smoke project links that target, and in
     its build directory `ninja -t deps | grep lib/btstack` lists the headers it used.
   - A file in the list that is missing fails the assembly.
4. Assemble and smoke-test locally on at least one platform. If the compiler, SDK,
   picotool or Python packages changed, also build a real project that uses them.

Use only releases that are at least two weeks old.

## Python build packages

`python/requirements-build.in` holds the build-time Python packages that projects built
with the bundle need.
`python/requirements.lock` pins them, with hashes for every platform.

**A project that needs a different package needs a toolchain release first.** Change
the `.in` file, then regenerate the lock:

```shell
uv pip compile python/requirements-build.in --universal --python-version 3.12 \
  --generate-hashes --exclude-newer <date two weeks ago> -o python/requirements.lock
```

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
