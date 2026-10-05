from __future__ import annotations

import re
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from app_paths import BASE_DIR


APACHE_DOWNLOAD_URL = "https://www.apachelounge.com/download/"
APACHE_BIN_DIR = BASE_DIR / "bin" / "apache"
TMP_DIR = BASE_DIR / "tmp"
APACHE_ZIP_PATTERN = re.compile(
    r"(?P<href>[^\"'<>\s]*httpd-(?P<version>2\.4\.\d+)[^\"'<>\s]*-win64-vs\d+\.zip)(?=[\"'<>\s])",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ApachePackage:
    version: str
    url: str
    filename: str

    @property
    def install_dir_name(self) -> str:
        return f"apache-{self.version}"


def fetch_latest_apache_packages(limit: int = 1) -> list[ApachePackage]:
    request = Request(APACHE_DOWNLOAD_URL, headers={"User-Agent": "LocalWAMP/1.0"})
    with urlopen(request, timeout=20) as response:
        html = response.read().decode("utf-8", errors="ignore")

    packages: dict[str, ApachePackage] = {}
    for match in APACHE_ZIP_PATTERN.finditer(html):
        href = match.group("href")
        version = match.group("version")
        url = urljoin(APACHE_DOWNLOAD_URL, href)
        packages.setdefault(version, ApachePackage(version=version, url=url, filename=Path(href).name))

    sorted_packages = sorted(packages.values(), key=lambda package: version_key(package.version), reverse=True)
    return sorted_packages[:limit]


def download_and_install_apache(
    package: ApachePackage,
    progress_callback: Callable[[int, int], None] | None = None,
) -> Path:
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    APACHE_BIN_DIR.mkdir(parents=True, exist_ok=True)

    target_dir = APACHE_BIN_DIR / package.install_dir_name
    if target_dir.exists():
        raise FileExistsError(f"La versione {package.install_dir_name} è già installata")

    zip_path = TMP_DIR / package.filename
    try:
        download_file(package.url, zip_path, progress_callback)
        target_dir.mkdir(parents=True, exist_ok=False)
        extract_apache_lounge_zip(zip_path, target_dir)
        return target_dir
    except Exception:
        if target_dir.exists():
            shutil.rmtree(target_dir, ignore_errors=True)
        raise
    finally:
        if zip_path.exists():
            zip_path.unlink()


def download_file(
    url: str,
    destination: Path,
    progress_callback: Callable[[int, int], None] | None = None,
) -> None:
    request = Request(url, headers={"User-Agent": "LocalWAMP/1.0"})
    with urlopen(request, timeout=30) as response:
        total = int(response.headers.get("Content-Length") or 0)
        downloaded = 0
        with destination.open("wb") as file:
            while True:
                chunk = response.read(1024 * 256)
                if not chunk:
                    break
                file.write(chunk)
                downloaded += len(chunk)
                if progress_callback:
                    progress_callback(downloaded, total)


def extract_apache_lounge_zip(zip_path: Path, target_dir: Path) -> None:
    target_root = target_dir.resolve()
    with zipfile.ZipFile(zip_path, "r") as archive:
        root_prefix = detect_apache_root_prefix(archive.namelist())
        for member in archive.infolist():
            source_name = member.filename.replace("\\", "/")
            if source_name.endswith("/"):
                continue

            relative_name = source_name[len(root_prefix) :] if root_prefix and source_name.startswith(root_prefix) else source_name
            if not relative_name:
                continue

            destination = (target_dir / relative_name).resolve()
            if target_root not in destination.parents and destination != target_root:
                raise RuntimeError(f"Percorso ZIP non sicuro: {source_name}")

            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, destination.open("wb") as output:
                shutil.copyfileobj(source, output)


def detect_apache_root_prefix(names: list[str]) -> str:
    for name in names:
        normalized = name.replace("\\", "/")
        if normalized.lower().startswith("apache24/"):
            return normalized[: len("Apache24/")]
    return ""


def version_key(version: str) -> tuple[int, int, int]:
    return tuple(int(part) for part in version.split("."))


