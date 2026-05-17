"""Build a distributable QGIS plugin ZIP archive."""

from __future__ import annotations

import argparse
import configparser
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parent
METADATA_FILE = ROOT / "metadata.txt"
PACKAGE_BASENAME = "drone_multispectral_vegetation_indices"
EXCLUDED_DIRS = {".git", "__pycache__", ".template_repo"}
EXCLUDED_FILES = {".DS_Store", ".gitignore", Path(__file__).name}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".zip"}


def plugin_version() -> str:
    """Read the plugin version from metadata.txt."""
    parser = configparser.ConfigParser()
    parser.read(METADATA_FILE)
    return parser.get("general", "version")


def default_zip_name() -> str:
    """Return the default package filename for the current plugin version."""
    return "{}-{}.zip".format(PACKAGE_BASENAME, plugin_version())


def output_path(requested_output: Path | None) -> Path:
    """Resolve the requested output location or use the repo-local default."""
    if requested_output is None:
        return ROOT / default_zip_name()

    requested_output = requested_output.expanduser()
    if requested_output.suffix.lower() != ".zip":
        requested_output = requested_output / default_zip_name()

    if not requested_output.is_absolute():
        requested_output = Path.cwd() / requested_output

    return requested_output.resolve()


def should_include(path: Path, archive_path: Path, destination: Path) -> bool:
    """Return whether a source file belongs in the plugin ZIP."""
    if path.resolve() == destination:
        return False

    if any(part in EXCLUDED_DIRS for part in archive_path.parts):
        return False

    if path.name in EXCLUDED_FILES:
        return False

    if path.suffix.lower() in EXCLUDED_SUFFIXES:
        return False

    return path.is_file()


def package_files(destination: Path) -> list[tuple[Path, Path]]:
    """Return source files and archive names for the plugin package."""
    files = []
    for path in sorted(ROOT.rglob("*")):
        archive_path = path.relative_to(ROOT)
        if should_include(path, archive_path, destination):
            files.append((path, Path(ROOT.name) / archive_path))

    return files


def build_zip(destination: Path) -> int:
    """Create the plugin ZIP and return the number of files added."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    files = package_files(destination)

    with ZipFile(destination, "w", compression=ZIP_DEFLATED) as archive:
        for source_path, archive_path in files:
            archive.write(source_path, archive_path.as_posix())

    return len(files)


def main() -> None:
    """Parse CLI arguments and build the plugin package."""
    parser = argparse.ArgumentParser(description="Build the QGIS plugin ZIP archive.")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output .zip path, or a directory that will receive the default ZIP filename.",
    )
    args = parser.parse_args()

    destination = output_path(args.output)
    file_count = build_zip(destination)
    print("Created {} with {} files.".format(destination, file_count))


if __name__ == "__main__":
    main()
