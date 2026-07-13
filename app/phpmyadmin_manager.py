from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Callable

from app_paths import BASE_DIR


PHPMYADMIN_SOURCE = BASE_DIR / "system" / "phpmyadmin"
PHPMYADMIN_LINK_NAME = "phpmyadmin"
ALLOW_NO_PASSWORD_LINE = "$cfg['Servers'][$i]['AllowNoPassword'] = true;"
ALLOW_NO_PASSWORD_PATTERN = re.compile(
    r"^\s*\$cfg\['Servers'\]\[\$i\]\['AllowNoPassword'\]\s*=\s*(?:true|false)\s*;",
    re.IGNORECASE,
)


def configure_phpmyadmin(document_root: str | Path, log_callback: Callable[[str], None] | None = None) -> bool:
    source = PHPMYADMIN_SOURCE.resolve()
    if not source.is_dir():
        _log(log_callback, "phpMyAdmin non trovato in system/phpmyadmin")
        return False

    configure_phpmyadmin_config(source)
    ensure_phpmyadmin_junction(Path(document_root).resolve(), source, log_callback)
    return True


def configure_phpmyadmin_config(source: Path) -> None:
    sample_config = source / "config.sample.inc.php"
    config = source / "config.inc.php"

    if not config.is_file():
        if not sample_config.is_file():
            raise FileNotFoundError(sample_config)
        shutil.copy2(sample_config, config)

    lines = config.read_text(encoding="utf-8", errors="ignore").splitlines()
    updated_lines: list[str] = []
    replaced = False

    for line in lines:
        if ALLOW_NO_PASSWORD_PATTERN.match(line):
            updated_lines.append(ALLOW_NO_PASSWORD_LINE)
            replaced = True
        else:
            updated_lines.append(line)

    if not replaced:
        updated_lines = inject_allow_no_password(updated_lines)

    config.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")


def inject_allow_no_password(lines: list[str]) -> list[str]:
    for index, line in enumerate(lines):
        if "$cfg['Servers'][$i]['auth_type']" in line:
            lines.insert(index + 1, ALLOW_NO_PASSWORD_LINE)
            return lines

    lines.append("")
    lines.append("$i++;" if not any("$i++" in line for line in lines) else "")
    lines.append(ALLOW_NO_PASSWORD_LINE)
    return [line for line in lines if line != ""]


def ensure_phpmyadmin_junction(document_root: Path, source: Path, log_callback: Callable[[str], None] | None = None) -> None:
    document_root.mkdir(parents=True, exist_ok=True)
    link_path = document_root / PHPMYADMIN_LINK_NAME

    if link_path.exists():
        _log(log_callback, f"phpMyAdmin gia disponibile in {link_path}")
        return

    command = ["cmd.exe", "/c", "mklink", "/J", str(link_path), str(source)]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")

    if result.returncode != 0:
        details = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"Creazione junction phpMyAdmin fallita: {details}")

    _log(log_callback, f"Junction phpMyAdmin creata: {link_path} -> {source}")


def _log(log_callback: Callable[[str], None] | None, message: str) -> None:
    if log_callback:
        log_callback(message)

