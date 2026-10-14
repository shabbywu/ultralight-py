"""Exercise the release gate with missing, incompatible and altered artifacts."""

import importlib.util
import io
import json
import tarfile
import zipfile
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("release", Path(__file__).parents[1] / "release.py")
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)
VERSION = "0.3.0"
PROJECT_VERSION = release.tomllib.loads((Path(__file__).parents[2] / "pyproject.toml").read_text())[
    "project"
]["version"]
COMMIT = "a" * 40


def make_sdist(directory, extra=None, missing=None):
    path = directory / f"ultralight_py-{VERSION}.tar.gz"
    files = {name: b"source" for name in release.SDIST_REQUIRED - set(missing or [])}
    files["PKG-INFO"] = f"Name: ultralight-py\nVersion: {VERSION}\n".encode()
    files.update(extra or {})
    with tarfile.open(path, "w:gz") as archive:
        for name, data in files.items():
            member = tarfile.TarInfo(f"ultralight_py-{VERSION}/{name}")
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
    return path


def make_wheel(directory, python, platform, abi=None):
    tag = f"{python}-{abi or python}-{platform}"
    path = directory / f"ultralight_py-{VERSION}-{tag}.whl"
    suffix = ".dll" if platform == "win_amd64" else ".dylib" if "macosx" in platform else ".so"
    with zipfile.ZipFile(path, "w") as wheel:
        info = f"ultralight_py-{VERSION}.dist-info"
        wheel.writestr(f"{info}/METADATA", f"Name: ultralight-py\nVersion: {VERSION}\n")
        wheel.writestr(f"{info}/WHEEL", f"Root-Is-Purelib: false\nTag: {tag}\n")
        for name in release.WHEEL_REQUIRED:
            wheel.writestr(name, b"")
        wheel.writestr(
            f"ultralight_py/_native.{python}.{'pyd' if suffix == '.dll' else 'so'}", b"native"
        )
        for library in ("UltralightCore", "WebCore", "Ultralight", "AppCore"):
            wheel.writestr(f"ultralight_py/{library}{suffix}", b"library")
    return path


@pytest.fixture
def matrix(tmp_path):
    directory = tmp_path / "dist"
    directory.mkdir()
    make_sdist(directory)
    for python in release.PYTHONS:
        for platform in ("manylinux_2_34_x86_64", "win_amd64", "macosx_11_0_arm64"):
            make_wheel(directory, python, platform)
    return directory


def test_complete_matrix(matrix):
    entries = release.inventory(matrix, "ultralight-py", VERSION)
    assert len(entries) == 16
    assert {entry["platform"] for entry in entries} == release.PLATFORMS | {"source"}


def test_missing_wheel_blocks_release(matrix):
    next(matrix.glob("*.whl")).unlink()
    with pytest.raises(ValueError, match="exactly 15 wheels"):
        release.inventory(matrix, "ultralight-py", VERSION)


@pytest.mark.parametrize(
    "platform", ["manylinux2014_x86_64", "musllinux_1_2_x86_64", "macosx_11_0_x86_64", "win32"]
)
def test_wrong_platform_blocks_release(tmp_path, platform):
    wheel = make_wheel(tmp_path, "cp313", platform)
    with pytest.raises(ValueError, match="platform"):
        release.check_wheel(wheel, "ultralight-py", VERSION)


def test_wrong_abi_blocks_release(tmp_path):
    wheel = make_wheel(tmp_path, "cp313", "win_amd64", "cp313t")
    with pytest.raises(ValueError, match="ABI"):
        release.check_wheel(wheel, "ultralight-py", VERSION)


@pytest.mark.parametrize(
    "name",
    [
        "externals/pybind11/.git",
        "build/CMakeCache.txt",
        "externals/ulbind17/sdk-cache/sdk.7z",
        "../escape",
    ],
)
def test_sdist_rejects_git_caches_and_traversal(tmp_path, name):
    sdist = make_sdist(tmp_path, extra={name: b"bad"})
    with pytest.raises(ValueError):
        release.check_sdist(sdist, "ultralight-py", VERSION)


def test_sdist_missing_dependency_blocks_release(tmp_path):
    sdist = make_sdist(tmp_path, missing=["externals/pybind11/CMakeLists.txt"])
    with pytest.raises(ValueError, match="missing required"):
        release.check_sdist(sdist, "ultralight-py", VERSION)


@pytest.mark.parametrize(
    "event,ref_type,tag,publish,allowed",
    [
        ("workflow_dispatch", "branch", "main", "false", True),
        ("workflow_dispatch", "branch", "main", "true", False),
        ("workflow_dispatch", "tag", f"v{PROJECT_VERSION}", "true", True),
        ("workflow_dispatch", "tag", "v0.0.0", "true", False),
        ("release", "tag", f"v{PROJECT_VERSION}", "false", True),
        ("release", "tag", PROJECT_VERSION, "false", False),
    ],
)
def test_publish_gate(monkeypatch, tmp_path, event, ref_type, tag, publish, allowed):
    monkeypatch.setenv("GITHUB_EVENT_NAME", event)
    monkeypatch.setenv("GITHUB_REF_TYPE", ref_type)
    monkeypatch.setenv("GITHUB_REF_NAME", tag)
    monkeypatch.setenv("RELEASE_TAG", tag)
    monkeypatch.setenv("PUBLISH", publish)
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "output"))
    monkeypatch.setattr(release.subprocess, "check_output", lambda *args, **kwargs: COMMIT)
    root = Path(__file__).parents[2]
    if allowed:
        release.validate(root)
        expected = event == "release" or publish == "true"
        assert f"publish={str(expected).lower()}" in (tmp_path / "output").read_text()
    else:
        with pytest.raises(ValueError):
            release.validate(root)


def test_manifest_rejects_tampering(monkeypatch, matrix, tmp_path):
    manifest = tmp_path / "manifest.json"
    common = [
        "--directory",
        str(matrix),
        "--manifest",
        str(manifest),
        "--version",
        VERSION,
        "--commit",
        COMMIT,
    ]
    monkeypatch.setattr("sys.argv", ["release.py", "assemble", *common])
    release.main()
    monkeypatch.setattr("sys.argv", ["release.py", "verify", *common])
    release.main()
    data = json.loads(manifest.read_text())
    data["commit"] = "b" * 40
    manifest.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="manifest"):
        release.main()
    monkeypatch.setattr("sys.argv", ["release.py", "assemble", *common])
    release.main()
    with next(matrix.glob("*.whl")).open("ab") as output:
        output.write(b"tampered")
    monkeypatch.setattr("sys.argv", ["release.py", "verify", *common])
    with pytest.raises(ValueError, match="manifest"):
        release.main()


def test_duplicate_target_blocks_release(matrix):
    replacement = matrix / f"ultralight.py-{VERSION}-cp310-cp310-win_amd64.whl"
    replacement.write_bytes(
        (matrix / f"ultralight_py-{VERSION}-cp310-cp310-win_amd64.whl").read_bytes()
    )
    (matrix / f"ultralight_py-{VERSION}-cp311-cp311-win_amd64.whl").unlink()
    with pytest.raises(ValueError, match="Duplicate wheel target"):
        release.inventory(matrix, "ultralight-py", VERSION)


def test_missing_library_blocks_release(tmp_path):
    path = make_wheel(tmp_path, "cp313", "win_amd64")
    with zipfile.ZipFile(path) as original:
        members = {name: original.read(name) for name in original.namelist()}
    del members["ultralight_py/Ultralight.dll"]
    with zipfile.ZipFile(path, "w") as wheel:
        for name, data in members.items():
            wheel.writestr(name, data)
    with pytest.raises(ValueError, match="Missing Ultralight dynamic library"):
        release.check_wheel(path, "ultralight-py", VERSION)


def test_cmake_version_mismatch_blocks_build(monkeypatch, tmp_path):
    monkeypatch.setenv("GITHUB_EVENT_NAME", "workflow_dispatch")
    monkeypatch.setenv("PUBLISH", "false")
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "ultralight-py"\nversion = "0.3.0"\n'
    )
    (tmp_path / "CMakeLists.txt").write_text("project(ultralight_py VERSION 0.4.0 LANGUAGES CXX)\n")
    with pytest.raises(ValueError, match="CMake and package versions"):
        release.validate(tmp_path)
