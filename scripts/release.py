"""Validate release inputs and the exact artifacts used by the publishing job.

Run with Python 3.11+ and packaging installed; no native SDK is needed.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import tarfile
import zipfile
from email.parser import BytesParser
from pathlib import Path, PurePosixPath

import tomllib
from packaging.utils import canonicalize_name, parse_sdist_filename, parse_wheel_filename

SDK_VERSION = "2.0.0-beta.2"
PYTHONS = {f"cp3{minor}" for minor in range(10, 15)}
PLATFORMS = {"linux-x64", "windows-x64", "macos-arm64"}
WHEEL_REQUIRED = {
    "ultralight_py/py.typed",
    "ultralight_py/appcore.py",
    "ultralight_py/appcore.pyi",
    "ultralight_py/registry.py",
    "ultralight_py/registry.pyi",
    "ultralight_py/__init__.pyi",
    "ultralight_py/api.pyi",
    "ultralight_py/input.pyi",
    "ultralight_py/objects.pyi",
    "ultralight_py/_waiting.py",
    "ultralight_py/events.py",
    "ultralight_py/events.pyi",
    "ultralight_py/scripting.py",
    "ultralight_py/scripting.pyi",
    "ultralight_py/integrations/asyncio.pyi",
    "ultralight_py/integrations/tkinter.pyi",
}
SDIST_REQUIRED = {
    "pyproject.toml",
    "CMakeLists.txt",
    "bindings/module.cpp",
    "bindings/images/conversion.hpp",
    "bindings/view/pixels.hpp",
    "bindings/appcore/bindings.hpp",
    "bindings/appcore/application.hpp",
    "bindings/appcore/window.hpp",
    "bindings/javascript/registry/api.hpp",
    "bindings/javascript/registry/attachments.hpp",
    "bindings/javascript/registry/bindings.hpp",
    "src/ultralight_py/appcore.py",
    "src/ultralight_py/registry.py",
    "src/ultralight_py/py.typed",
    "src/ultralight_py/_waiting.py",
    "src/ultralight_py/events.py",
    "src/ultralight_py/events.pyi",
    "src/ultralight_py/scripting.py",
    "src/ultralight_py/scripting.pyi",
    "externals/pybind11/CMakeLists.txt",
    "externals/pybind11/include/pybind11/pybind11.h",
    "externals/ulbind17/CMakeLists.txt",
    "externals/ulbind17/include/ulbind17/ulbind17.hpp",
    "externals/ulbind17/ultralight-sdk/SDK.cmake",
    "externals/ulbind17/embedded/GenerateResource.cmake",
    "externals/ulbind17/embedded/ulbind17/fonts/FreeUniversal-Regular.cpp",
    "externals/ulbind17/embedded/ulbind17/fonts/AlimamaShuHeiTi-Bold.cpp",
    "scripts/test_wheel.py",
    "tests/test_integration.py",
    "tests/cases.py",
    "tests/__init__.py",
    "tests/wait_fakes.py",
    "tests/waiting_cases.py",
}
FORBIDDEN_PARTS = {
    ".git",
    "__pycache__",
    ".venv",
    ".ruff_cache",
    ".pytest_cache",
    "build",
    "sdk-cache",
    "CMakeFiles",
    "_skbuild",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate(root):
    project = tomllib.loads((root / "pyproject.toml").read_text())["project"]
    name, version = project["name"], project["version"]
    require(name == "ultralight-py", f"Unexpected package name: {name}")
    require(re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version), "Expected X.Y.Z package version")
    cmake = (root / "CMakeLists.txt").read_text()
    match = re.search(r"project\(ultralight_py\s+VERSION\s+([0-9.]+)\s", cmake)
    require(match and match[1] == version, "CMake and package versions must match")
    require(f'set(ULTRALIGHT_SDK_VERSION "{SDK_VERSION}"' in cmake, "SDK version changed")
    event = os.environ.get("GITHUB_EVENT_NAME", "workflow_dispatch")
    publish = event == "release" or os.environ.get("PUBLISH", "false") == "true"
    if publish:
        require(os.environ.get("GITHUB_REF_TYPE") == "tag", "Publishing requires a tag ref")
        tag = (
            os.environ.get("RELEASE_TAG")
            if event == "release"
            else os.environ.get("GITHUB_REF_NAME")
        )
        require(tag == f"v{version}", f"Release tag must be v{version}, got {tag!r}")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    values = {"name": name, "version": version, "commit": commit, "publish": str(publish).lower()}
    print(json.dumps(values, indent=2))
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as output:
            output.writelines(f"{key}={value}\n" for key, value in values.items())


def check_metadata(data, name, version):
    metadata = BytesParser().parsebytes(data)
    require(
        canonicalize_name(metadata["Name"] or "") == canonicalize_name(name),
        "Metadata name mismatch",
    )
    require(metadata["Version"] == version, "Metadata version mismatch")


def check_sdist(path, name, version, destination=None):
    parsed_name, parsed_version = parse_sdist_filename(path.name)
    require(
        parsed_name == canonicalize_name(name) and str(parsed_version) == version,
        "sdist filename mismatch",
    )
    with tarfile.open(path) as archive:
        members = archive.getmembers()
        paths = [PurePosixPath(member.name) for member in members]
        require(len(paths) == len(set(paths)), "Duplicate sdist members")
        roots = {path.parts[0] for path in paths if path.parts}
        require(len(roots) == 1, "sdist must have one root directory")
        files = set()
        for member, member_path in zip(members, paths):
            require(
                not member_path.is_absolute() and ".." not in member_path.parts, "Unsafe sdist path"
            )
            require(member.isfile() or member.isdir(), "sdist contains a link or special file")
            relative = PurePosixPath(*member_path.parts[1:])
            require(
                not FORBIDDEN_PARTS.intersection(relative.parts),
                f"Cache/Git data in sdist: {relative}",
            )
            require(
                relative.name != "CMakeCache.txt" and relative.suffix != ".pyc",
                f"Build data in sdist: {relative}",
            )
            if member.isfile():
                files.add(str(relative))
        require(
            SDIST_REQUIRED <= files,
            f"sdist missing required sources: {sorted(SDIST_REQUIRED - files)}",
        )
        root = next(iter(roots))
        check_metadata(archive.extractfile(f"{root}/PKG-INFO").read(), name, version)
        if destination:
            destination.mkdir(parents=True, exist_ok=True)
            archive.extractall(destination, filter="data")
            # The workflow uses a fixed path on every platform.
            (destination / root).rename(destination / "source")


def check_wheel(path, name, version):
    parsed_name, parsed_version, build, tags = parse_wheel_filename(path.name)
    require(
        parsed_name == canonicalize_name(name) and str(parsed_version) == version and not build,
        "Wheel name/version/build mismatch",
    )
    interpreters = {tag.interpreter for tag in tags}
    require(len(interpreters) == 1 and interpreters <= PYTHONS, "Unexpected Python interpreter")
    interpreter = next(iter(interpreters))
    require({tag.abi for tag in tags} == {interpreter}, "Unexpected Python ABI")
    platforms = {tag.platform for tag in tags}
    if platforms == {"manylinux_2_34_x86_64"}:
        platform = "linux-x64"
    elif platforms == {"win_amd64"}:
        platform = "windows-x64"
    elif platforms == {"macosx_11_0_arm64"}:
        # Wheel tags normalize macOS 11.x to 11_0; deployment target is 11.3.
        platform = "macos-arm64"
    else:
        raise ValueError(f"Unexpected wheel platform tags: {platforms}")
    with zipfile.ZipFile(path) as wheel:
        names = wheel.namelist()
        require(len(names) == len(set(names)), "Duplicate wheel members")
        metadata = [entry for entry in names if entry.endswith(".dist-info/METADATA")]
        require(len(metadata) == 1, "Wheel must contain one METADATA file")
        check_metadata(wheel.read(metadata[0]), name, version)
        wheel_metadata = BytesParser().parsebytes(
            wheel.read(metadata[0].replace("METADATA", "WHEEL"))
        )
        filename_tags = {str(tag) for tag in tags}
        require(
            set(wheel_metadata.get_all("Tag", [])) == filename_tags, "Internal wheel tags mismatch"
        )
        require(wheel_metadata["Root-Is-Purelib"] == "false", "Expected a native wheel")
        require(WHEEL_REQUIRED <= set(names), "Missing type declarations/py.typed")
        suffix = {"linux-x64": ".so", "windows-x64": ".dll", "macos-arm64": ".dylib"}[platform]
        for library in ("UltralightCore", "WebCore", "Ultralight", "AppCore"):
            require(
                any(
                    re.match(rf"^(?:lib)?{library}(?:[-.]|$)", PurePosixPath(entry).name)
                    and entry.endswith(suffix)
                    for entry in names
                ),
                f"Missing {library} dynamic library",
            )
        require(
            any(
                entry.startswith("ultralight_py/_native.") and entry.endswith((".so", ".pyd"))
                for entry in names
            ),
            "Missing native extension",
        )
    return interpreter, platform


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def inventory(directory, name, version):
    files = sorted(directory.iterdir())
    require(
        len(files) == 16 and all(path.is_file() for path in files),
        "Expected exactly 15 wheels and one sdist",
    )
    seen = set()
    entries = []
    sdists = 0
    for path in files:
        if path.name.endswith(".whl"):
            identity = check_wheel(path, name, version)
            require(identity not in seen, f"Duplicate wheel target: {identity}")
            seen.add(identity)
            platform = identity[1]
        elif path.name.endswith(".tar.gz"):
            check_sdist(path, name, version)
            sdists += 1
            platform = "source"
        else:
            raise ValueError(f"Unexpected release file: {path.name}")
        entries.append(
            {
                "filename": path.name,
                "sha256": digest(path),
                "size": path.stat().st_size,
                "platform": platform,
            }
        )
    require(
        sdists == 1
        and seen == {(python, platform) for python in PYTHONS for platform in PLATFORMS},
        "Incomplete wheel matrix",
    )
    return entries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["validate", "sdist", "assemble", "verify"])
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--directory", type=Path, default=Path("dist"))
    parser.add_argument("--name", default="ultralight-py")
    parser.add_argument("--version")
    parser.add_argument("--commit")
    parser.add_argument("--manifest", type=Path, default=Path("release-manifest/manifest.json"))
    parser.add_argument("--extract", type=Path)
    args = parser.parse_args()
    if args.command == "validate":
        validate(args.root)
        return
    require(args.version, "--version is required")
    if args.command == "sdist":
        files = list(args.directory.iterdir())
        require(len(files) == 1 and files[0].is_file(), "Expected one sdist")
        check_sdist(files[0], args.name, args.version, args.extract)
        return
    require(
        args.commit and re.fullmatch(r"[0-9a-f]{40}", args.commit), "--commit must be a source SHA"
    )
    manifest = {
        "name": args.name,
        "version": args.version,
        "commit": args.commit,
        "sdk": SDK_VERSION,
        "files": inventory(args.directory, args.name, args.version),
    }
    if args.command == "assemble":
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(json.dumps(manifest, indent=2) + "\n")
        args.manifest.with_name("SHA256SUMS").write_text(
            "".join(f"{entry['sha256']}  {entry['filename']}\n" for entry in manifest["files"])
        )
    else:
        require(
            json.loads(args.manifest.read_text()) == manifest,
            "Release manifest/provenance/SHA-256 mismatch",
        )
    print(f"Verified {len(manifest['files'])} release packages for {args.version} ({args.commit})")


if __name__ == "__main__":
    main()
