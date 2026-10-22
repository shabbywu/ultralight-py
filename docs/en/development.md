# Development guide

Source builds, testing, and local environments. Users can start with the [README](../../README.md).
See [Architecture](architecture.md) for implementation boundaries and [Releasing](releasing.md) for release steps.

## Installing from source

Dependencies use the `externals/pybind11` and `externals/ulbind17` submodules.
You need Python 3.10+, CMake 3.22+, and a C++20 compiler.

```sh
git submodule update --init --recursive
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test,dev]'
python -c "import ultralight_py"
```

Ultralight 2.0.0-beta.2 SDK is downloaded by default. To supply a local SDK:

```sh
python -m pip install -e . -Ccmake.define.ULTRALIGHT_SDK_ROOT=/absolute/path/to/sdk
```

Local validation primarily targets macOS ARM64 and ordinary GIL Python 3.13.
The package requires Python 3.10+, but individual Python versions have not all completed local validation.
Linux x64 and Windows x64 retain dependency build support; full Python-binding validation on those platforms remains pending.
pybind11 is pinned to v3.0.4, ulbind17 to `3a31b4b`, and the default SDK to 2.0.0-beta.2.

## Building and testing distributions

Replace the installation path below with the wheel generated in `dist/`:

```sh
python -m pip install build
python -m build
python -m pip install --force-reinstall /path/to/built.whl
python -m pytest tests -q
```

Wheels include the native extension, UltralightCore, WebCore, Ultralight, and AppCore shared libraries, and embedded resources.
Local wheel tags depend on the build environment. ARM64 wheels do not work on other architectures,
and a build on the current system does not validate older macOS compatibility.
The sdist includes pinned submodule sources; consumers do not need to fetch submodules separately.
Supply the SDK explicitly for offline builds. Default downloading reuses ulbind17's version pinning, checksums, and cache.
Tests isolate Runtime scenarios in subprocesses and cover offscreen rendering, navigation, callback release, threads,
exceptions, HTTP, local/virtual resources, input reentry, object isolation, live containers, binding revocation, and exit cleanup.
Tk tests cover simulated platform events and real windows; real-window cases skip when Tk or a display service is unavailable.

## Container read benchmarks

After installing the current source, run:

```sh
python scripts/benchmark_containers.py
python scripts/benchmark_containers.py --sizes 16 1024 --reads 1 10 100 1000 10000 --iterations 7
```

Each container size runs in a separate process, covering JS reads of Python list indices, dict fields, length,
nested fields, and map/reduce. JSON Lines output includes environment, copy-only time, and median/min/max timings
for live proxies, pre-copied data, and copying plus reads. All paths validate identical results.
Samples are interleaved after warm-up to reduce execution-order bias, allowing comparison of live/copy crossover points at different access counts.

Use the same interpreter, Release build, and arguments for before/after comparisons, reinstalling the corresponding source each time.
Times include evaluate() overhead; machine load and JIT state affect results.
Benchmarks do not become fixed timing assertions in pytest.
See [Frequent reads](objects.md#frequent-reads) for shared semantics and snapshot choices.

Local reference results for the first optimization round: macOS ARM64, Python 3.13.0, Release build,
size=1024, median of 7 runs after 2 warm-ups. The first four scenarios perform 10,000 reads; map/reduce traverses once.
Nested data is a list of dicts containing a value field.

| Scenario | Live before | Live after | Speedup | Copy + read after, including copy |
| --- | ---: | ---: | ---: | ---: |
| list index | 32.56 ms | 11.11 ms | 2.9× | 1.02 ms |
| dict field | 28.40 ms | 8.80 ms | 3.2× | 0.92 ms |
| nested field | 78.31 ms | 20.61 ms | 3.8× | 2.74 ms |
| list length | 20.69 ms | 8.25 ms | 2.5× | 0.87 ms |
| map/reduce | 6.37 ms | 2.39 ms | 2.7× | 0.78 ms |

In the same measurement, reading a 1024-element list 100 times took about 0.12 ms live and 0.71 ms including copying;
at 1000 reads, about 1.11 ms and 0.71 ms respectively.
The optimization reduces fixed live-access overhead. Explicit snapshots can further reduce bridge crossings for dense computation;
the crossover varies with data and environment.

The second round further reduces temporary Handles for scalar returns and nested proxy reuse, uses private numeric opcodes,
and passes array indices as numbers. Remeasuring both rounds with the same environment/arguments at size=1024:

| Scenario | First round, remeasured | Second round | Additional speedup |
| --- | ---: | ---: | ---: |
| list index | 11.42 ms | 8.86 ms | 1.29× |
| dict field | 9.16 ms | 6.46 ms | 1.42× |
| nested field | 19.89 ms | 16.75 ms | 1.19× |
| list length | 8.18 ms | 5.66 ms | 1.45× |
| map/reduce | 2.28 ms | 1.73 ms | 1.32× |

The second round preserves live sharing, safe integer ranges, Unicode conversion, subclasses, and lifecycle semantics.
Explicit copying remains faster for dense computation; these figures represent local measurements only.

## macOS Tk development environment

For Tk examples, use ordinary GIL Python 3.13 with Homebrew Tcl/Tk 8.6.
For example, with Python 3.13.16:

```sh
brew install tcl-tk@8
env PYTHON_BUILD_HOMEBREW_TCLTK_FORMULA=tcl-tk@8 \
    PYTHON_BUILD_TCLTK_USE_PKGCONFIG=1 \
    PKG_CONFIG_PATH="$(brew --prefix tcl-tk@8)/lib/pkgconfig" \
    pyenv install 3.13.16
pyenv local 3.13.16
python -m tkinter
python -m venv .venv
source .venv/bin/activate
python -m pip install build ninja '.[test,dev]'
```

`python -m tkinter` must create a window; installing tkinter's Python source alone does not make the `_tkinter` extension available.
This interpreter is for development/real-window validation; the distribution still declares Python 3.10+.

For bidirectional Promise/asyncio bridging and optional scheduled driving, see the [API](api.md)
and [example](../../examples/async_bridge.py).

## Python linting and formatting

Development dependencies pin Ruff. Run lint and format checks separately:

```bash
python -m pip install -e '.[test,dev]'
python -m ruff check .
python -m ruff format --check .

# Apply safe fixes and format.
python -m ruff check --fix .
python -m ruff format .
```

`pyproject.toml` configures a 100-column width, double quotes, spaces, and LF endings.
Formatting covers source, type stubs, tests, and examples; externals, build, and dist are excluded.
`ruff check` includes checks such as unused imports; `ruff format --check` only checks formatting.
Type stubs use `typing_extensions.Self` to retain Python 3.10 support.

## AppCore validation

```sh
python -m pytest tests/test_registry.py tests/test_appcore.py -q
python examples/appcore.py --smoke
python examples/appcore.py --cpu --smoke
```

AppCore tests need a native macOS desktop session.
Other platforms retain registry regression and package-loading validation;
validate native interaction on each system following the [Window guide](appcore.md#platform-validation).
