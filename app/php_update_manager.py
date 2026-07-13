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


PHP_DOWNLOAD_URL = "https://windows.php.net/download/"
PHP_RELEASES_URL = "https://windows.php.net/downloads/releases/"
PHP_BIN_DIR = BASE_DIR / "bin" / "php"
TMP_DIR = BASE_DIR / "tmp"
PHP_ZIP_PATTERN = re.compile(
    r"(?P<href>[^\"'<>\s]*php-(?P<version>\d+\.\d+\.\d+)-Win32-vs(?:16|17)-x64\.zip)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class PhpPackage:
    version: str
    url: str
    filename: str

    @property
    def install_dir_name(self) -> str:
        return f"php-{self.version}"


def fetch_latest_php_packages(limit: int = 3) -> list[PhpPackage]:
    packages: dict[str, PhpPackage] = {}
    collect_packages(PHP_DOWNLOAD_URL, packages)
    if len(packages) < limit:
        collect_packages(PHP_RELEASES_URL, packages)

    sorted_packages = sorted(packages.values(), key=lambda package: version_key(package.version), reverse=True)
    return sorted_packages[:limit]


def collect_packages(page_url: str, packages: dict[str, PhpPackage]) -> None:
    request = Request(page_url, headers={"User-Agent": "LocalPHP/1.0"})
    with urlopen(request, timeout=20) as response:
        html = response.read().decode("utf-8", errors="ignore")

    for match in PHP_ZIP_PATTERN.finditer(html):
        href = match.group("href")
        lower_href = href.lower()
        if "nts" in lower_href:
            continue

        version = match.group("version")
        url = urljoin(page_url, href)
        packages.setdefault(version, PhpPackage(version=version, url=url, filename=Path(href).name))


def download_and_install_php(
    package: PhpPackage,
    progress_callback: Callable[[int, int], None] | None = None,
) -> Path:
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    PHP_BIN_DIR.mkdir(parents=True, exist_ok=True)

    target_dir = PHP_BIN_DIR / package.install_dir_name
    if target_dir.exists():
        raise FileExistsError(f"La versione {package.install_dir_name} è già installata")

    zip_path = TMP_DIR / package.filename
    try:
        download_file(package.url, zip_path, progress_callback)
        target_dir.mkdir(parents=True, exist_ok=False)
        with zipfile.ZipFile(zip_path, "r") as archive:
            archive.extractall(target_dir)
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
    request = Request(url, headers={"User-Agent": "LocalPHP/1.0"})
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


def version_key(version: str) -> tuple[int, int, int]:
    return tuple(int(part) for part in version.split("."))

