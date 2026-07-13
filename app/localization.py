from __future__ import annotations

import json
import locale
from pathlib import Path
from typing import Any

from app_paths import BASE_DIR


LANGUAGE_LABELS = {
    "en": "English",
    "it": "Italiano",
    "es": "Español",
}
DEFAULT_LANGUAGE = "en"
LANGUAGES_DIR = BASE_DIR / "system" / "languages"


def detect_default_language() -> str:
    language = (locale.getlocale()[0] or locale.getdefaultlocale()[0] or "").lower()
    if language.startswith("it"):
        return "it"
    if language.startswith("es"):
        return "es"
    return DEFAULT_LANGUAGE


def language_code_from_label(label: str) -> str | None:
    for code, language_label in LANGUAGE_LABELS.items():
        if language_label == label:
            return code
    return None


class LocalizationManager:
    def __init__(self, language: str | None = None) -> None:
        self.language = language if language in LANGUAGE_LABELS else detect_default_language()
        self._fallback = self._load(DEFAULT_LANGUAGE)
        self._translations = self._load(self.language)

    def set_language(self, language: str) -> None:
        self.language = language if language in LANGUAGE_LABELS else DEFAULT_LANGUAGE
        self._translations = self._load(self.language)

    def t(self, key: str, **kwargs: Any) -> str:
        value = self._translations.get(key, self._fallback.get(key, key))
        if kwargs:
            try:
                return value.format(**kwargs)
            except (KeyError, ValueError):
                return value
        return value

    @staticmethod
    def _load(language: str) -> dict[str, str]:
        path = LANGUAGES_DIR / f"{language}.json"
        try:
            return json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            return {}
