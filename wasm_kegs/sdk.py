#!/usr/bin/env python3
import argparse
import json
import os
import shutil
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path


class KegBuildError(Exception):
    pass


def load_toml(path: Path):
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except Exception as e:
        raise KegBuildError(f"Failed to parse TOML file {path}: {e}")


def validate_keg_structure(root: Path):
    """Validate keg.toml and basic plugin structure."""
    keg_path = root / "keg.toml"
    if not keg_path.exists():
        raise KegBuildError("Missing keg.toml")

    keg = load_toml(keg_path)

    if "name" not in keg["keg"] or "version" not in keg["keg"]:
        raise KegBuildError("keg.toml must specify name and version")

    plugins = keg.get("plugins")
    if not isinstance(plugins, list):
        raise KegBuildError("[[plugins]] table missing or not a list")

    for entry in plugins:
        plugin_name = entry.get("name")

        if "path" in entry:
            path = root / entry["path"]
            if not (path / "metadata.toml").exists():
                raise KegBuildError(
                    f"{plugin_name}: {path}/metadata.toml missing"
                )
        else:
            path = root / "plugins" / plugin_name
            if not path.exists():
                raise KegBuildError(f"{plugin_name}: {path} missing")

        metadata = load_toml(path / "metadata.toml")

        if metadata["plugin"].get("name") != plugin_name:
            raise KegBuildError(
                f"{plugin_name}: metadata.toml name does not match keg.toml name"
            )

        # Optional schema.toml
        schema_name = metadata.get("schema")
        if schema_name:
            if not (path / schema_name).exists():
                raise KegBuildError(
                    f"{plugin_name}: schema.toml declared but not found"
                )


def build_rust_crates(root: Path, plugin_dir: Path):
    """Build all crates under src/rust and place wasm files in plugin/."""
    out_dir = root / plugin_dir

    crate = out_dir / "src" / "rust"

    # Arbitrary name
    if crate.exists():
        x = os.listdir(crate)
        if len(x) > 1:
            raise KegBuildError(f"Multiple rust crates found in {crate}")

        crate = crate / x[0]

    print(f"[build] Building Rust crate in {crate}")
    print(f"[build] Outputting to {out_dir}")

    if not crate.exists():
        print(f"[build] {crate} does not exist")
        return

    out_dir.mkdir(exist_ok=True, parents=True)

    if not crate.is_dir():
        print(f"[build] {crate} is not a directory")
        return

    cargo_toml = crate / "Cargo.toml"
    if not cargo_toml.exists():
        raise KegBuildError(f"[build] Cargo.toml not found in {crate}")

    with open(cargo_toml, "rb") as f:
        cargo = tomllib.load(f)

    print(f"[build] Building Rust crate {crate}")

    # Perform cargo build
    result = subprocess.run(
        [
            "cargo",
            "build",
            "--release",
            "--target",
            "wasm32-unknown-unknown",
        ],
        cwd=crate,
        stdout=sys.stdout,
        stderr=sys.stderr,
    )

    if result.returncode != 0:
        raise KegBuildError(f"Cargo build failed for {crate}")

    md = subprocess.check_output(["cargo", "metadata"], cwd=crate)
    md = json.loads(md)

    # Find the WASM artifact
    artifact = (
        Path(md["target_directory"])
        / "wasm32-unknown-unknown"
        / "release"
        / (cargo["package"]["name"].replace("-", "_") + ".wasm")
    )

    if not artifact.exists():
        raise KegBuildError(f"Expected wasm file not found: {artifact}")

    # Copy to output
    dest = out_dir / "plugin.wasm"
    shutil.copyfile(artifact, dest)
    print(f"[build] Wrote {dest}")

    # Debug build

    # Perform cargo build
    result = subprocess.run(
        [
            "cargo",
            "build",
            "--target",
            "wasm32-unknown-unknown",
        ],
        cwd=crate,
        stdout=sys.stdout,
        stderr=sys.stderr,
    )

    if result.returncode != 0:
        raise KegBuildError(f"Cargo build failed for {crate}")

    # Find the WASM artifact
    # Find the WASM artifact
    artifact = (
        Path(md["target_directory"])
        / "wasm32-unknown-unknown"
        / "debug"
        / (cargo["package"]["name"].replace("-", "_") + ".wasm")
    )

    if not artifact.exists():
        raise KegBuildError(f"Expected wasm file not found: {artifact}")

    # Copy to output
    dest = out_dir / "plugin.debug.wasm"
    shutil.copyfile(artifact, dest)
    print(f"[build] Wrote {dest}")


def collect_paths_for_archive(root: Path, include_source: bool):
    """Yield (archive_name, real_path) tuples."""
    root_base = os.path.basename(root)
    print(f"[pack] Scanning {root_base} for files")
    for path in root.rglob("*"):
        p = Path(os.path.relpath(path, root))
        # Exclude dist folder
        if p.parts[0] == "dist":
            continue

        if p.parts[0].startswith("."):
            continue

        if p.parts[-1] == "plugin.debug.wasm":
            continue

        # Exclude .git or other noise
        if ".git" in path.parts:
            continue

        if path.is_dir():
            continue

        if p.parts[0] == "plugins":
            if p.parts[2] == "test":
                if not include_source:
                    continue
            if p.parts[2] == "src":
                if not include_source:
                    continue
                if p.parts[5] == "target":
                    continue

        print(f"[pack] Including {p}")

        arcname = path.relative_to(root)
        yield arcname.as_posix(), path


def build_keg(root: Path):
    keg = load_toml(root / "keg.toml")
    name = keg["keg"]["name"]
    version = keg["keg"]["version"]
    include_source = keg.get("include_source", False)

    validate_keg_structure(root)

    # Build plugins
    for entry in keg["plugins"]:
        plugin_dir = Path(entry.get("path", "plugins/" + entry["name"]))
        build_rust_crates(root, plugin_dir)

    # Prepare dist output
    dist = root / "dist"
    dist.mkdir(exist_ok=True)
    out_file = dist / f"{name}-{version}.keg"

    print(f"[pack] Creating {out_file}")

    # Build zip archive
    with zipfile.ZipFile(
        out_file,
        "w",
        compression=zipfile.ZIP_LZMA,
        compresslevel=9,
    ) as z:
        for arcname, realpath in collect_paths_for_archive(
            root, include_source
        ):
            z.write(realpath, arcname)

    print(f"[done] Built {out_file}")


def main():
    parser = argparse.ArgumentParser(description="Keg Builder")
    sub = parser.add_subparsers(dest="command", required=True)

    build_cmd = sub.add_parser("build", help="Build and package the .keg file")
    build_cmd.add_argument(
        "path", nargs="?", default=".", help="Path to keg root"
    )

    args = parser.parse_args()

    try:
        if args.command == "build":
            root = Path(args.path).resolve()
            build_keg(root)
    except KegBuildError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
