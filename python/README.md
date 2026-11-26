# Python packages

These packages are installed into the bundled Python 3.12 (`tools/python`), on every
platform.

| File | Role |
| --- | --- |
| `requirements-build.in` | The packages projects use directly, each pinned with `==` and a short comment on what it is for. Edit this file. |
| `requirements.lock` | Generated. Every package, dependencies included, with sha256 hashes for every platform. Never edit by hand. |

The assembler installs the lock with `pip --only-binary=:all: --no-deps --require-hashes`.
Console scripts are dropped, so packages run as `python -m <module>`.

## Adding or updating a package

1. **Check the wheels.** The package and each of its dependencies need a release at
   least two weeks old. That release needs a wheel for each target:

   | Target | Wheel tags |
   | --- | --- |
   | Linux x86_64 | `cp312`/`abi3`, `manylinux` (glibc 2.34 or older) |
   | Linux aarch64 | `cp312`/`abi3`, `manylinux` (glibc 2.34 or older) |
   | macOS | arm64 or universal2 |
   | Windows | amd64 |

   A pure-Python (`py3-none-any`) wheel covers every target. Packages that exist only as
   an sdist cannot be used.
2. **Edit `requirements-build.in`:** set the exact version, with a comment.
3. **Regenerate the lock** with any `uv`, for example the bundle's
   `tools/uv/uv`:

   ```shell
   uv pip compile python/requirements-build.in --universal --python-version 3.12 \
     --generate-hashes --exclude-newer <YYYY-MM-DD> -o python/requirements.lock
   ```

   `--exclude-newer` keeps every dependency at least two weeks old:
   - When adding a package, keep the date from the lock's header, so the existing pins
     stay as they are.
   - To refresh everything, use today minus 14 days.

   In the lock's diff, check that only the packages you meant to change moved.
4. **Update the version check:** the `check` of the `python-packages` component in
   `manifest.json`. Import the new module and print its version. Put the expected
   output in `expect`.
5. **Update the docs:** the package list in `README.md`, and the Python packages row in
   `THIRD_PARTY.md`, with the licence of every new package in the lock.
6. **Test:** assemble and smoke-test locally (see CONTRIBUTING.md), then open a pull
   request. CI installs the lock on all four platforms, so a missing wheel fails there.

## Projects

A project can use a new package once it pins a toolchain release that contains the
package. Until then, its builds fall back to their own environment.
