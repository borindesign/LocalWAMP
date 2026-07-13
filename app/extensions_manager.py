from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import customtkinter as ctk

from php_ini_config import ensure_extension_dir, normalize_extension_name


EXTENSION_PATTERN = re.compile(
    r"^(?P<indent>\s*)(?P<comment>;?)(?P<body>\s*extension\s*=\s*(?P<value>.+?)\s*)$",
    re.IGNORECASE,
)

BOOLEAN_OPTIONS = (
    "allow_url_fopen",
    "display_errors",
    "log_errors",
    "short_open_tag",
    "expose_php",
)

TEXT_OPTIONS = (
    "max_execution_time",
    "max_input_time",
    "post_max_size",
    "upload_max_filesize",
    "max_file_uploads",
    "max_input_vars",
)


@dataclass(frozen=True)
class ExtensionLine:
    index: int
    name: str
    enabled: bool


class PhpSettingsPanel(ctk.CTkFrame):
    def __init__(
        self,
        master,
        php_ini_getter: Callable[[], Path | None],
        apache_running_callback: Callable[[], bool],
        restart_apache_callback: Callable[[], None],
        log_callback: Callable[[str], None] | None = None,
        translation_callback: Callable[..., str] | None = None,
    ) -> None:
        super().__init__(master, corner_radius=12)

        self.php_ini_getter = php_ini_getter
        self.apache_running_callback = apache_running_callback
        self.restart_apache_callback = restart_apache_callback
        self.log_callback = log_callback
        self._translation_callback = translation_callback
        self.extension_vars: dict[int, ctk.BooleanVar] = {}
        self.boolean_vars: dict[str, ctk.BooleanVar] = {}
        self.text_entries: dict[str, ctk.CTkEntry] = {}

        self._build_layout()
        self.reload()

    def t(self, key: str, **kwargs) -> str:
        if self._translation_callback:
            return self._translation_callback(key, **kwargs)
        return key.format(**kwargs) if kwargs else key

    def _build_layout(self) -> None:
        self.tabs = ctk.CTkTabview(self, corner_radius=12)
        self.tabs.pack(fill="both", expand=True, padx=14, pady=14)

        self.extensions_tab = self.tabs.add(self.t("php_extensions_tab"))
        self.options_tab = self.tabs.add(self.t("php_options_tab"))

        self.extensions_scroll = ctk.CTkScrollableFrame(self.extensions_tab)
        self.extensions_scroll.pack(fill="both", expand=True, padx=12, pady=(12, 8))

        self.options_frame = ctk.CTkScrollableFrame(self.options_tab)
        self.options_frame.pack(fill="both", expand=True, padx=12, pady=(12, 8))

        self.actions_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.actions_frame.pack(fill="x", padx=14, pady=(0, 14))

        self.save_button = ctk.CTkButton(
            self.actions_frame,
            text=self.t("save_php_settings"),
            width=190,
            command=self.save,
        )
        self.save_button.pack(side="left")

        self.reload_button = ctk.CTkButton(
            self.actions_frame,
            text=self.t("reload"),
            width=100,
            command=self.reload,
        )
        self.reload_button.pack(side="left", padx=10)

        self.status_label = ctk.CTkLabel(self.actions_frame, text="")
        self.status_label.pack(side="left", padx=8)

    def reload(self) -> None:
        for widget in self.extensions_scroll.winfo_children():
            widget.destroy()
        for widget in self.options_frame.winfo_children():
            widget.destroy()

        self.extension_vars.clear()
        self.boolean_vars.clear()
        self.text_entries.clear()

        php_ini_path = self.php_ini_getter()
        if not php_ini_path or not php_ini_path.is_file():
            self._set_status(self.t("select_valid_php"), "#ffb020")
            self.save_button.configure(state="disabled")
            return

        self.save_button.configure(state="normal")
        lines = php_ini_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        self._load_extensions(lines)
        self._load_options(lines)
        self._set_status(f"php.ini caricato: {php_ini_path.name}", "#2cc985")

    def save(self) -> None:
        php_ini_path = self.php_ini_getter()
        if not php_ini_path or not php_ini_path.is_file():
            self._set_status(self.t("php_ini_not_found"), "#ff5c5c")
            return

        lines = php_ini_path.read_text(encoding="utf-8", errors="ignore").splitlines()

        for line_index, variable in self.extension_vars.items():
            if line_index < len(lines):
                lines[line_index] = self._set_extension_enabled(lines[line_index], variable.get())

        for key, variable in self.boolean_vars.items():
            lines = self._set_option_value(lines, key, "On" if variable.get() else "Off")

        for key, entry in self.text_entries.items():
            lines = self._set_option_value(lines, key, entry.get().strip())

        php_ini_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self._set_status(self.t("php_settings_saved"), "#2cc985")
        self._log(self.t("php_saved_in", path=php_ini_path))

        if self.apache_running_callback():
            self._set_status(self.t("apache_restart_required"), "#ffb020")
            self.restart_apache_callback()

    def _load_extensions(self, lines: list[str]) -> None:
        extension_lines = [
            extension_line
            for index, line in enumerate(lines)
            if (extension_line := self._parse_extension_line(index, line))
        ]

        if not extension_lines:
            label = ctk.CTkLabel(
                self.extensions_scroll,
                text=self.t("no_extensions_found"),
                text_color="#ffb020",
            )
            label.pack(anchor="w", padx=8, pady=8)
            return

        for extension_line in extension_lines:
            variable = ctk.BooleanVar(value=extension_line.enabled)
            checkbox = ctk.CTkCheckBox(
                self.extensions_scroll,
                text=extension_line.name,
                variable=variable,
            )
            checkbox.pack(anchor="w", padx=8, pady=5)
            self.extension_vars[extension_line.index] = variable

    def _load_options(self, lines: list[str]) -> None:
        title = ctk.CTkLabel(
            self.options_frame,
            text=self.t("php_options_title"),
            font=ctk.CTkFont(size=15, weight="bold"),
        )
        title.pack(anchor="w", padx=8, pady=(4, 10))

        for key in BOOLEAN_OPTIONS:
            variable = ctk.BooleanVar(value=self._read_boolean_option(lines, key))
            checkbox = ctk.CTkCheckBox(self.options_frame, text=key, variable=variable)
            checkbox.pack(anchor="w", padx=8, pady=5)
            self.boolean_vars[key] = variable

        separator = ctk.CTkFrame(self.options_frame, height=1, fg_color="#3a3a3a")
        separator.pack(fill="x", padx=8, pady=14)

        for key in TEXT_OPTIONS:
            row = ctk.CTkFrame(self.options_frame, fg_color="transparent")
            row.pack(fill="x", padx=8, pady=5)
            row.grid_columnconfigure(1, weight=1)

            label = ctk.CTkLabel(row, text=key, width=170, anchor="w")
            label.grid(row=0, column=0, sticky="w", padx=(0, 10))

            entry = ctk.CTkEntry(row)
            entry.insert(0, self._read_option_value(lines, key))
            entry.grid(row=0, column=1, sticky="ew")
            self.text_entries[key] = entry

    @staticmethod
    def _parse_extension_line(index: int, line: str) -> ExtensionLine | None:
        match = EXTENSION_PATTERN.match(line)
        if not match:
            return None

        value = match.group("value").split(";", 1)[0].strip().strip('"').strip("'")
        name = Path(value).name.removesuffix(".dll")
        return ExtensionLine(index=index, name=name, enabled=match.group("comment") != ";")

    @staticmethod
    def _set_extension_enabled(line: str, enabled: bool) -> str:
        match = EXTENSION_PATTERN.match(line)
        if not match:
            return line

        indent = match.group("indent")
        body = match.group("body").lstrip()
        return f"{indent}{body}" if enabled else f"{indent};{body}"

    @staticmethod
    def _read_option_value(lines: list[str], key: str) -> str:
        pattern = re.compile(rf"^\s*;?\s*{re.escape(key)}\s*=\s*(?P<value>.*?)\s*$", re.IGNORECASE)
        for line in lines:
            match = pattern.match(line)
            if match:
                return match.group("value").split(";", 1)[0].strip()
        return ""

    @classmethod
    def _read_boolean_option(cls, lines: list[str], key: str) -> bool:
        value = cls._read_option_value(lines, key).lower()
        return value in {"1", "on", "true", "yes"}

    @staticmethod
    def _set_option_value(lines: list[str], key: str, value: str) -> list[str]:
        pattern = re.compile(rf"^\s*;?\s*{re.escape(key)}\s*=", re.IGNORECASE)
        replacement = f"{key} = {value}"

        for index, line in enumerate(lines):
            if pattern.match(line):
                lines[index] = replacement
                return lines

        lines.append(replacement)
        return lines

    def _set_status(self, message: str, color: str) -> None:
        self.status_label.configure(text=message, text_color=color)

    def _log(self, message: str) -> None:
        if self.log_callback:
            self.log_callback(message)



