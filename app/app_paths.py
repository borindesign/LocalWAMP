from __future__ import annotations

import sys
from pathlib import Path


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = get_base_dir()


def resource_path(relative_path: str) -> Path:
    """Resolve read-only assets in source and PyInstaller onedir builds."""
    resource_root = Path(getattr(sys, "_MEIPASS", BASE_DIR))
    return resource_root / relative_path
