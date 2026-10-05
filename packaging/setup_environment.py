from __future__ import annotations

import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import urljoin

APP_DIR = Path(__file__).resolve().parent.parent / 'app'
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from app_paths import BASE_DIR

try:
    import requests
    from bs4 import BeautifulSoup
except ModuleNotFoundError:
    print(
        "Per favore, installa le dipendenze necessarie eseguendo: "
        "pip install requests beautifulsoup4"
    )
    raise SystemExit(1)


PROJECT_ROOT = BASE_DIR
APACHE_DIR = PROJECT_ROOT / "bin" / "apache"
MYSQL_DIR = PROJECT_ROOT / "bin" / "mysql"

APACHE_DOWNLOAD_PAGE = "https://www.apachelounge.com/download/"
MYSQL_DOWNLOAD_PAGE = "https://dev.mysql.com/downloads/mysql/"
APACHE_PATTERN = "win64-VS16.zip"
MYSQL_PATTERN = r"mysql-.*winx64.*\.zip"


class SetupEnvironmentError(Exception):
    pass


def version_key(value: str) -> tuple[int, ...]:
    numbers = re.findall(r"\d+", value)
    return tuple(int(number) for number in numbers)


def get_page(url: str) -> str:
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.text


def get_links(url: str) -> list[str]:
    soup = BeautifulSoup(get_page(url), "html.parser")
    links = []

    for tag in soup.find_all("a", href=True):
        links.append(urljoin(url, tag["href"]))

    return links


def get_latest_url(url: str, pattern: str) -> str | None:
    links = get_links(url)
    regex = re.compile(pattern, re.IGNORECASE)
    matches = [
        link
        for link in links
        if pattern.lower() in link.lower() or regex.search(link)
    ]

    if not matches:
        return None

    return sorted(matches, key=version_key, reverse=True)[0]


def get_download_page_url(url: str) -> str:
    links = get_links(url)
    download_links = [
        link
        for link in links
        if "download" in link.lower() or "downloads" in link.lower()
    ]

    if not download_links:
        return url

    return sorted(download_links, key=version_key, reverse=True)[0]


def download_file(url: str, destination: Path) -> None:
    with requests.get(url, stream=True, timeout=60) as response:
        response.raise_for_status()
        with destination.open("wb") as file:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    file.write(chunk)


def safe_extract(zip_path: Path, destination: Path) -> None:
    destination_root = destination.resolve()

    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.infolist():
            target_path = (destination / member.filename).resolve()
            if not target_path.is_relative_to(destination_root):
                raise SetupEnvironmentError(f"Percorso non sicuro nello zip: {member.filename}")

        archive.extractall(destination)


def archive_content_root(extracted_dir: Path) -> Path:
    items = [item for item in extracted_dir.iterdir() if item.name != "__MACOSX"]
    if len(items) == 1 and items[0].is_dir():
        return items[0]
    return extracted_dir


def copy_tree_contents(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)

    for item in source.iterdir():
        target = destination / item.name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True)
        else:
            shutil.copy2(item, target)


def find_executable(directory: Path, executable_name: str) -> Path:
    matches = sorted(directory.rglob(executable_name), key=lambda path: len(path.parts))
    if not matches:
        raise SetupEnvironmentError(
            f"{executable_name} non trovato dopo l'estrazione in {directory}"
        )
    return matches[0]


def install_zip(url: str, destination: Path, executable_name: str, temp_dir: Path) -> Path:
    zip_path = temp_dir / f"{destination.name}.zip"
    extract_dir = temp_dir / f"{destination.name}_extract"
    extract_dir.mkdir(parents=True, exist_ok=True)

    download_file(url, zip_path)
    safe_extract(zip_path, extract_dir)
    copy_tree_contents(archive_content_root(extract_dir), destination)

    return find_executable(destination, executable_name)


def setup_environment() -> tuple[Path, Path | None]:
    apache_url = get_latest_url(APACHE_DOWNLOAD_PAGE, APACHE_PATTERN)
    if apache_url is None:
        raise SetupEnvironmentError("Nessun archivio Apache win64-VS16.zip trovato.")

    mysql_url = get_latest_url(MYSQL_DOWNLOAD_PAGE, MYSQL_PATTERN)

    with tempfile.TemporaryDirectory(prefix="localwamp_setup_") as temp:
        temp_dir = Path(temp)
        apache_exe = install_zip(apache_url, APACHE_DIR, "httpd.exe", temp_dir)
        mysql_exe = None

        if mysql_url:
            mysql_exe = install_zip(mysql_url, MYSQL_DIR, "mysqld.exe", temp_dir)

    return apache_exe, mysql_exe


def main() -> None:
    apache_exe, mysql_exe = setup_environment()

    print(f"Apache installato: {apache_exe}")

    if mysql_exe:
        print(f"MySQL installato: {mysql_exe}")
        return

    download_page = get_download_page_url(MYSQL_DOWNLOAD_PAGE)
    print(
        "Ho trovato questa pagina di download: "
        f"{download_page}. Vai qui, clicca su 'No thanks, just start my download' "
        "e copia l'URL che ottieni"
    )


if __name__ == "__main__":
    main()





