# Release guide

This guide describes distribution builds, validation, and PyPI publication.
For local builds, see [Building and testing distributions](development.md#building-and-testing-distributions).

## Builds and triggers

The [Wheels workflow](../../.github/workflows/wheels.yml) builds ordinary GIL CPython 3.10–3.14 packages
for Windows x64, Linux x64, and macOS ARM64: 15 wheels and one source distribution.
Linux targets glibc 2.34. The macOS deployment target is 11.3, with a `macosx_11_0_arm64` wheel tag.
The native extension and UltralightCore, WebCore, Ultralight, and AppCore libraries ship in the packages.

Run `Wheels` manually in GitHub Actions with `publish=false` to build a branch without publishing.
For a release, align versions in `pyproject.toml` and `CMakeLists.txt`, create the matching `vX.Y.Z` tag,
and publish its GitHub Release. Alternatively, select that tag manually and enable `publish`.
Only a tag matching the package version can publish; creating a tag alone does not trigger publication.

The workflow validates the sdist first, then builds wheels from it.
auditwheel, delocate, and delvewheel repair dynamic-library dependencies, followed by installation/testing in isolated environments.
Source commit and SDK version are pinned. After checks pass, the workflow produces release artifacts;
approval publishes those exact files without recompiling.

## Downloads and validation

The run summary provides `release-packages` and `release-manifest`, retained for 30 days.
The former contains wheels and sdist; the latter contains `manifest.json` and `SHA256SUMS`,
recording source commit, SDK version, file sizes, platforms, and checksums.

Use Python 3.11+ to verify the full artifact set, replacing version and commit SHA with the build's values:

```sh
python -m pip install packaging
python scripts/release.py verify --directory /path/to/release-packages \
  --manifest /path/to/release-manifest/manifest.json \
  --version 0.6.1 --commit FULL_COMMIT_SHA
```

Create a fresh virtual environment on each target platform and install its matching wheel.
Copy `tests/`, `examples/`, and `scripts/test_wheel.py` from the sdist into another empty directory,
preserving relative paths, and run there:

```sh
python -m pip install /absolute/path/to/matching.whl \
  'pytest>=8,<10' 'pytest-asyncio>=1,<2' 'Pillow>=11,<13' 'numpy>=1.26,<3'
python -I scripts/test_wheel.py
```

Validation uses SDK libraries bundled in the wheel, without an external SDK.
Linux needs Xvfb, X11, fonts, and related system libraries; run `xvfb-run -a python -I scripts/test_wheel.py`.
The dependency list is in `pyproject.toml`. Tk/AppCore native-window cases require a desktop;
AppCore desktop tests currently target macOS.
Also run the [window example](../../examples/appcore.py) to check Chinese fonts, IME, resizing, and multi-display DPI.

## Approval and publication

After confirming installation, resources, pixels, input, object bridging, Session, asyncio, and cleanup results,
approve `pypi` on the run's deployment review page.
Files and manifest are verified again before uploading to PyPI.
Rejecting approval prevents uploading; an existing package version causes publication to fail.
Expired artifacts require a new build and validation.

Maintainers must configure external services:

- In GitHub, protect the `pypi` environment with `shabbywu` as reviewer, allow self-review,
  disallow administrator bypass, and restrict deployments to `v*` tags.
  Enable these rules in GitHub; naming an environment in YAML does not create protection rules.
  See [Deployment environments](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments).
- In PyPI, configure a trusted publisher for `ultralight-py`: owner `shabbywu`, repository `ultralight-py`,
  workflow `wheels.yml`, environment `pypi`. Publication uses OIDC without a stored API token.
  See [Trusted publisher setup](https://docs.pypi.org/trusted-publishers/using-a-publisher/).

Only the publication job has `id-token: write`; other jobs have `contents: read` only.
