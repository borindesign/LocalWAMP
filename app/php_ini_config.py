from __future__ import annotations

import shutil
import re
from pathlib import Path
from typing import Iterable

from app_paths import BASE_DIR


DEFAULT_PHP_EXTENSIONS = ("mysqli", "pdo_mysql", "mbstring")
EXTENSION_PATTERN = re.compile(
    r"^(?P<indent>\s*)(?P<comment>;?)(?P<body>\s*extension\s*=\s*(?P<value>.+?)\s*)$",
    re.IGNORECASE,
)


def ensure_php_ini(php_dir: str | Path) -> Path:
    php_path = Path(php_dir).resolve()
    php_ini = php_path / "php.ini"
    php_ini_development = php_path / "php.ini-development"

    if not php_ini.is_file():
        if not php_ini_development.is_file():
            raise FileNotFoundError(php_ini_development)
        shutil.copy2(php_ini_development, php_ini)

    configure_php_ini_defaults(php_ini)
    return php_ini


def configure_php_ini_defaults(
    php_ini_path: str | Path,
    default_extensions: Iterable[str] = DEFAULT_PHP_EXTENSIONS,
) -> None:
    path = Path(php_ini_path).resolve()
    php_dir = path.parent
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    lines = set_php_option(lines, "extension_dir", f'"{(php_dir / "ext").resolve().as_posix()}"')

    default_extension_names = tuple(default_extensions)
    for extension_name in default_extension_names:
        lines = set_extension_enabled(lines, extension_name, True)
    lines = dedupe_extension_lines(lines, default_extension_names)

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def ensure_extension_dir(php_ini_path: str | Path) -> None:
    path = Path(php_ini_path).resolve()
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    lines = set_php_option(lines, "extension_dir", f'"{(path.parent / "ext").resolve().as_posix()}"')
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def set_php_option(lines: list[str], key: str, value: str) -> list[str]:
    pattern = re.compile(rf"^\s*;?\s*{re.escape(key)}\s*=", re.IGNORECASE)
    replacement = f"{key} = {value}"

    for index, line in enumerate(lines):
        if pattern.match(line):
            lines[index] = replacement
            return lines

    lines.append(replacement)
    return lines


def set_extension_enabled(lines: list[str], extension_name: str, enabled: bool) -> list[str]:
    target = normalize_extension_name(extension_name)

    for index, line in enumerate(lines):
        match = EXTENSION_PATTERN.match(line)
        if not match:
            continue

        current_name = normalize_extension_name(match.group("value"))
        if current_name != target:
            continue

        indent = match.group("indent")
        body = match.group("body").lstrip()
        lines[index] = f"{indent}{body}" if enabled else f"{indent};{body}"
        return lines

    if enabled:
        lines.append(f"extension={target}")

    return lines


def normalize_extension_name(value: str) -> str:
    clean_value = value.split(";", 1)[0].strip().strip('"').strip("'")
    name = Path(clean_value).name
    return name.removesuffix(".dll").removeprefix("php_").lower()

def dedupe_extension_lines(lines: list[str], extension_names: Iterable[str]) -> list[str]:
    targets = {normalize_extension_name(name) for name in extension_names}
    seen: set[str] = set()
    deduped: list[str] = []

    for line in lines:
        match = EXTENSION_PATTERN.match(line)
        if not match:
            deduped.append(line)
            continue

        name = normalize_extension_name(match.group("value"))
        if name in targets:
            if name in seen:
                continue
            seen.add(name)

        deduped.append(line)

    return deduped


