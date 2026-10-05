"""Build LocalWAMP; optionally reuse runtimes from a distributed release ZIP."""
from __future__ import annotations
import argparse
import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VERSION = "1.3.0"

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-archive", type=Path, help="Distributed ZIP containing bin/ and system/phpmyadmin/")
    args = parser.parse_args()
    for module in ("PyInstaller", "customtkinter", "PIL"):
        if importlib.util.find_spec(module) is None:
            parser.error(f"Missing build dependency: {module}. See README.md.")
    if args.runtime_archive and not args.runtime_archive.is_file():
        parser.error(f"Runtime archive not found: {args.runtime_archive}")
    subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
         "--distpath", str(PROJECT_ROOT / "dist"), "--workpath", str(PROJECT_ROOT / "build"),
         str(PROJECT_ROOT / "packaging" / "LocalWAMP.spec")], cwd=PROJECT_ROOT, check=True,
    )
    output = PROJECT_ROOT / "dist" / "LocalWAMP"
    shutil.copytree(PROJECT_ROOT / "system" / "languages", output / "system" / "languages", dirs_exist_ok=True)
    shutil.copyfile(PROJECT_ROOT / "LICENSE", output / "LICENSE")
    if args.runtime_archive:
        with zipfile.ZipFile(args.runtime_archive) as archive:
            for entry in archive.infolist():
                if not entry.filename.startswith(("bin/", "system/phpmyadmin/")):
                    continue
                destination = (output / entry.filename).resolve()
                if not destination.is_relative_to(output.resolve()):
                    raise ValueError(f"Unsafe archive entry: {entry.filename}")
                if entry.is_dir():
                    destination.mkdir(parents=True, exist_ok=True)
                else:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(entry) as source, destination.open("wb") as target:
                        shutil.copyfileobj(source, target)
        (output / "www").mkdir(exist_ok=True)
        (output / "README.txt").write_text(
            f"LocalWAMP v{VERSION}\n\n"
            "Extract the whole folder and run LocalWAMP.exe. No Python installation is required.\n"
            "Place your projects in www/ or choose a document root in Settings.\n"
            "Keep bin/, system/, _internal/ and settings.json beside the executable.\n"
            "Existing LocalPHP settings and Apache configuration blocks are supported.\n"
            "Close the manager before updating. Back up your projects and MySQL data.\n"
            "For an existing installation, replace only the manager, _internal/ and\n"
            "system/languages/; preserve settings.json, bin/ and project folders.\n"
            "Remove the old LocalPHP-Manager.exe after replacing it with LocalWAMP.exe.\n", encoding="utf-8",
        )
        releases = PROJECT_ROOT / "releases"
        releases.mkdir(exist_ok=True)
        zip_path = releases / f"LocalWAMP-v{VERSION}.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(output.rglob("*")):
                if path.is_file():
                    archive.write(path, (Path("LocalWAMP") / path.relative_to(output)).as_posix())
        print(f"Portable release: {zip_path}")
    print(f"Executable: {output / 'LocalWAMP.exe'}")

if __name__ == "__main__":
    main()
