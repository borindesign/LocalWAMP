from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from app_paths import BASE_DIR


APACHE_ROOT = BASE_DIR / "bin" / "apache"
PHP_ROOT = BASE_DIR / "bin" / "php"
MYSQL_EXE = BASE_DIR / "bin" / "mysql" / "bin" / "mysqld.exe"

NO_VERSION_FOUND = "Nessuna versione trovata"


@dataclass(frozen=True)
class RuntimeVersion:
    label: str
    root: Path
    executable: Path | None = None


def version_sort_key(value: str) -> tuple[int, ...]:
    numbers = re.findall(r"\d+", value)
    return tuple(int(number) for number in numbers) or (0,)


def find_apache_versions(root: Path = APACHE_ROOT) -> list[RuntimeVersion]:
    candidates = _candidate_dirs(root)
    versions = []

    for candidate in candidates:
        executable = _find_first(candidate, ("bin/httpd.exe", "httpd.exe"))
        if executable:
            versions.append(RuntimeVersion(candidate.name, candidate, executable))

    return _sort_versions(_dedupe_versions(versions))


def find_php_versions(root: Path = PHP_ROOT) -> list[RuntimeVersion]:
    candidates = _candidate_dirs(root)
    versions = []

    for candidate in candidates:
        if _looks_like_php_dir(candidate):
            executable = _find_first(candidate, ("php.exe",))
            versions.append(RuntimeVersion(candidate.name, candidate, executable))

    return _sort_versions(_dedupe_versions(versions))


def _candidate_dirs(root: Path) -> list[Path]:
    if not root.exists():
        return []

    candidates = []
    if root.is_dir():
        candidates.append(root)
        candidates.extend(path for path in root.iterdir() if path.is_dir())

    return candidates


def _looks_like_php_dir(path: Path) -> bool:
    markers = (
        "php.exe",
        "php.ini",
        "php.ini-development",
        "php8apache2_4.dll",
    )
    return any((path / marker).is_file() for marker in markers)


def _find_first(root: Path, relative_paths: tuple[str, ...]) -> Path | None:
    for relative_path in relative_paths:
        path = root / relative_path
        if path.is_file():
            return path
    return None


def _dedupe_versions(versions: list[RuntimeVersion]) -> list[RuntimeVersion]:
    seen = set()
    unique = []

    for version in versions:
        key = version.executable.resolve() if version.executable else version.root.resolve()
        if key in seen:
            continue
        seen.add(key)
        unique.append(version)

    return unique


def _sort_versions(versions: list[RuntimeVersion]) -> list[RuntimeVersion]:
    return sorted(
        versions,
        key=lambda version: (version_sort_key(version.label), version.label.lower()),
        reverse=True,
    )



