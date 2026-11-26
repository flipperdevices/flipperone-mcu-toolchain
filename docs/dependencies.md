# Dependencies and `manifest.json`

`manifest.json` lists everything a bundle contains: each component's upstream source,
its version, and the sha256 it must match. The Python packages are the exception; they
live in [`python/`](../python/README.md).

## Updating a component

Use only upstream releases that are at least two weeks old.

1. **Edit the component in `manifest.json`.** Typical changes:
   - `version` and the asset URLs
   - `root`, `exe`, `path` or `license_files`, if the archive layout changed
   - `check.expect`
2. **Refill the hashes.** Blank them (`"sha256": ""`, or `"commit": ""` for git), then:

   ```shell
   GITHUB_TOKEN=$(gh auth token) python3 -m assembler.pin --write
   python3 -m assembler.pin    # every line must say ok
   ```

   `pin` takes each hash from upstream metadata where there is any:
   - GitHub release digests
   - xPack `.sha` files
   - PyPI
   - `git ls-remote`

   snapshot.debian.org packages are hashed from a download.
3. **Update the versions** in `README.md` and `THIRD_PARTY.md`.
4. **Assemble and smoke-test** locally on at least one platform. If the compiler, the SDK,
   picotool or the Python packages changed, also build a real project with the bundle.
   - A Linux bundle has to be assembled on Linux; Docker works.
   - Keep the output directory off a case-insensitive filesystem, such as a macOS bind
     mount.

**Per kind:**
- **deb:**
  - Take the package from `https://snapshot.debian.org/archive/debian/<first_seen>/pool/...`;
    the snapshot API (`/mr/binary/<package>/`) lists versions and their `first_seen`.
  - Check its glibc floor:

    ```shell
    readelf -V <lib> | grep -o 'GLIBC_[0-9.]*' | sort -uV | tail -1
    ```

    The result must be 2.34 or older.
  - Point `files` at the real file, not the soname symlink.
- **Linux binaries:**
  - A new binary may need libraries that aren't bundled; `readelf -d` lists them.
  - Ship each missing library as a `deb` component.
  - Set `runpath` on the binary, so it loads them from `tools/lib`.
  - The smoke test's `ldd` check fails if a library is missing or comes from the system.
- **patchelf:** bump `patchelf.version` and its three wheel URLs, then run `pin`.

## `manifest.json` reference

**Top level:**

| Key | Meaning |
| --- | --- |
| `schema` | `1` |
| `platforms` | Bundles to build, from `linux-x86_64`, `linux-aarch64`, `darwin-arm64` and `windows-x64` |
| `patchelf` | `version`, `license`, `homepage`, and `assets`: one `{url, sha256}` wheel per host platform the assembler runs on. Sets `runpath`s. |
| `components` | Installed in this order |

**Every component:**

| Key | Meaning |
| --- | --- |
| `name` | Unique. Becomes `licenses/<name>/`, and the key in the bundle's and the release's `toolchain.json` / `release.json`. |
| `kind` | `archive`, `git`, `pip` or `deb` |
| `version`, `license`, `homepage` | Recorded in the bundle and the release. `license` is an SPDX expression; `homepage` must be https. |
| `dest` | Install directory under the bundle root: relative and POSIX. Not for `pip`. Must not overlap another component's, except that `deb` components share one. |
| `license_files` | Optional. fnmatch patterns, relative to the unpacked source, copied to `licenses/<name>/`. Each must match a file. |
| `path`, `path_windows` | Optional. Directories under `dest` added to PATH, in manifest order; `.` is `dest` itself. `path_windows` replaces `path` on Windows. |
| `exe` | Optional. Main executable under `dest`, as `"bin/x"` or `{"unix": …, "windows": …}`; `.exe` is added on Windows. |
| `check` | `{args, expect}`. The smoke test runs `exe` (for `pip`, the interpreter) with `args` and looks for `expect` in the output. Required with `exe` and for `pip`. |

**Per kind:**

| Kind | Keys |
| --- | --- |
| `archive` | `assets`: per platform (or `any`), `{url, sha256}`, plus optional `root` and `exclude` (fnmatch patterns to skip). `root` selects what gets installed: unset installs the single top-level directory, or the whole archive if there isn't exactly one; `""` installs the archive root; a path installs that directory. Optional: `root` at component level as the default, `restamp_pyc` (Python trees), and `runpath` (Linux only: RUNPATH set on `exe`, starting with `$ORIGIN`). |
| `git` | `url`, `ref` (the tag), `commit` (full sha1). Optional: `submodules`, `{path: commit}`, which checks out only these; `keep`, `{submodule path: [files]}`, which keeps only those files. |
| `pip` | `interpreter`: the name of an earlier component. `requirements`: the lock file. |
| `deb` | `assets`: per Linux platform, `{url, sha256, files}`, where `files` maps an installed soname to its path in the package (`usr/lib/<triplet>/lib….so.N.M`). Installed only on the listed platforms. Each file gets RUNPATH `$ORIGIN`. |

`assembler/manifest.py` validates all of this, and `tests/test_manifest.py` runs it.
