import atexit
import ctypes
from datetime import datetime
import json
import sys
from pathlib import Path
import threading
import time
from tkinter import filedialog
import webbrowser

import customtkinter as ctk

from app_paths import BASE_DIR, resource_path
from localization import LANGUAGE_LABELS, LocalizationManager, detect_default_language, language_code_from_label

from apache_update_manager import ApachePackage, download_and_install_apache, fetch_latest_apache_packages

from configure_apache_php import DEFAULT_DOCUMENT_ROOT
from extensions_manager import PhpSettingsPanel
from phpmyadmin_manager import configure_phpmyadmin
from php_update_manager import PhpPackage, download_and_install_php, fetch_latest_php_packages
from runtime_scanner import (
    MYSQL_EXE,
    NO_VERSION_FOUND,
    RuntimeVersion,
    find_apache_versions,
    find_php_versions,
)
from server_manager import ServerManager


ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("dark-blue")

SETTINGS_FILE = BASE_DIR / "settings.json"
DEFAULT_SETTINGS = {
    "mysql_path": "bin/mysql/bin/mysqld.exe",
    "document_root": DEFAULT_DOCUMENT_ROOT.relative_to(BASE_DIR).as_posix(),
    "apache_port": "80",
    "mysql_port": "3306",
    "lang": detect_default_language(),
}


def load_settings() -> dict[str, str]:
    if not SETTINGS_FILE.exists():
        resolve_setting_path(DEFAULT_SETTINGS["document_root"]).mkdir(parents=True, exist_ok=True)
        save_settings(DEFAULT_SETTINGS)
        return DEFAULT_SETTINGS.copy()

    try:
        settings = json.loads(SETTINGS_FILE.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError):
        settings = {}

    merged_settings = DEFAULT_SETTINGS | {
        key: str(value)
        for key, value in settings.items()
        if key in DEFAULT_SETTINGS and value is not None and str(value).strip()
    }
    merged_settings["mysql_path"] = path_to_setting(resolve_setting_path(merged_settings["mysql_path"]))
    merged_settings["document_root"] = path_to_setting(resolve_setting_path(merged_settings["document_root"]))
    if merged_settings["lang"] not in LANGUAGE_LABELS:
        merged_settings["lang"] = detect_default_language()
    resolve_setting_path(merged_settings["document_root"]).mkdir(parents=True, exist_ok=True)
    save_settings(merged_settings)
    return merged_settings


def save_settings(settings: dict[str, str]) -> None:
    SETTINGS_FILE.write_text(json.dumps(settings, indent=4, ensure_ascii=False), encoding="utf-8")


def resolve_setting_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else BASE_DIR / path


def path_to_setting(value: str | Path) -> str:
    path = Path(value).resolve()
    try:
        return path.relative_to(BASE_DIR).as_posix()
    except ValueError:
        return str(path)


def safe_port(value: str, fallback: int) -> int:
    try:
        port = int(str(value).strip())
    except ValueError:
        return fallback
    return port if 1 <= port <= 65535 else fallback


class LocalWAMPApp(ctk.CTk):
    def __init__(self) -> None:
        if sys.platform == "win32":
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Borindesign.LocalWAMP")
        super().__init__()
        if sys.platform == "win32":
            self.iconbitmap(str(resource_path("assets/localwamp.ico")))

        self.settings = load_settings()
        self.i18n = LocalizationManager(self.settings.get("lang"))
        self.title(self.t("app_title"))
        self.geometry("1100x800")
        self.minsize(980, 700)
        self._is_closing = False
        self.apache_versions: list[RuntimeVersion] = []
        self.php_versions: list[RuntimeVersion] = []
        self.apache_by_label: dict[str, RuntimeVersion] = {}
        self.php_by_label: dict[str, RuntimeVersion] = {}
        self.server_manager = ServerManager(log_callback=self._threadsafe_log)

        self._scan_runtimes()
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        atexit.register(self.on_closing)

        self.title(self.t("app_title"))
        self._build_layout()
        self.configure_phpmyadmin()
        self._apply_runtime_state()
        self._update_connection_boxes()
        self.after(2000, self._refresh_server_statuses)

    def t(self, key: str, **kwargs) -> str:
        return self.i18n.t(key, **kwargs)

    def change_language(self, language_label: str) -> None:
        language_code = language_code_from_label(language_label)
        if not language_code:
            return

        self.i18n.set_language(language_code)
        self.settings["lang"] = language_code
        save_settings(self.settings)
        self._rebuild_layout_after_language_change()
        self.log(self.t("log_language_changed"))

    def _current_language_label(self) -> str:
        return LANGUAGE_LABELS.get(self.settings.get("lang", "en"), LANGUAGE_LABELS["en"])

    def _rebuild_layout_after_language_change(self) -> None:
        if hasattr(self, "container"):
            self.container.destroy()
        self.title(self.t("app_title"))
        self._build_layout()
        self.configure_phpmyadmin()
        self._apply_runtime_state()
        self._update_connection_boxes()

    def _scan_runtimes(self) -> None:
        self.apache_versions = find_apache_versions()
        self.php_versions = find_php_versions()
        self.apache_by_label = {version.label: version for version in self.apache_versions}
        self.php_by_label = {version.label: version for version in self.php_versions}

    def _build_layout(self) -> None:
        self.container = ctk.CTkFrame(self, corner_radius=16)
        self.container.pack(fill="both", expand=True, padx=18, pady=18)

        self.tabs = ctk.CTkTabview(self.container, corner_radius=12)
        self.tabs.pack(fill="both", expand=True, padx=16, pady=16)

        self.dashboard_tab = self.tabs.add(self.t("tab_dashboard"))
        self.php_tab = self.tabs.add(self.t("tab_php"))
        self.download_tab = self.tabs.add(self.t("tab_download"))
        self.settings_tab = self.tabs.add(self.t("tab_settings"))

        self._build_dashboard_tab()
        self._build_php_tab()
        self._build_download_tab()
        self._build_settings_tab()

    def _status_block(self, parent, title: str):
        frame = ctk.CTkFrame(parent, corner_radius=12)
        frame.pack(fill="x", padx=16, pady=10)

        label = ctk.CTkLabel(
            frame,
            text=self.t("status_inactive", service=title),
            text_color="#ff5c5c",
            font=ctk.CTkFont(size=16, weight="bold"),
        )
        label.pack(side="left", padx=16, pady=16)

        button = ctk.CTkButton(frame, text=self.t("start"), width=120)
        button.pack(side="right", padx=16, pady=16)

        return label, button

    def _build_dashboard_tab(self) -> None:
        self.apache_status_label, self.apache_start_button = self._status_block(self.dashboard_tab, "Apache")
        self.apache_start_button.configure(command=self.toggle_apache)

        self.mysql_status_label, self.mysql_start_button = self._status_block(self.dashboard_tab, "MySQL")
        self.mysql_start_button.configure(command=self.toggle_mysql)

        selector_frame = ctk.CTkFrame(self.dashboard_tab, corner_radius=12)
        selector_frame.pack(fill="x", padx=16, pady=(8, 10))
        selector_frame.grid_columnconfigure((0, 1, 2), weight=1)

        php_label = ctk.CTkLabel(selector_frame, text=self.t("php_version"))
        php_label.grid(row=0, column=0, sticky="w", padx=16, pady=(16, 6))

        apache_label = ctk.CTkLabel(selector_frame, text=self.t("apache_version"))
        apache_label.grid(row=0, column=1, sticky="w", padx=16, pady=(16, 6))

        self.php_version_combobox = ctk.CTkComboBox(
            selector_frame,
            values=self._php_combo_values(),
            state="readonly" if self.php_versions else "disabled",
            command=lambda _value: self._apply_runtime_state(),
        )
        self.php_version_combobox.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 16))
        self._bind_dropdown_open(self.php_version_combobox)

        self.apache_version_combobox = ctk.CTkComboBox(
            selector_frame,
            values=self._apache_combo_values(),
            state="readonly" if self.apache_versions else "disabled",
            command=lambda _value: self._apply_runtime_state(),
        )
        self.apache_version_combobox.grid(row=1, column=1, sticky="ew", padx=16, pady=(0, 16))
        self._bind_dropdown_open(self.apache_version_combobox)

        refresh_button = ctk.CTkButton(selector_frame, text=self.t("rescan"), width=120, command=self.refresh_runtime_versions)
        refresh_button.grid(row=1, column=2, sticky="ew", padx=16, pady=(0, 16))

        self.connection_frame = ctk.CTkFrame(self.dashboard_tab, corner_radius=12)
        self.connection_frame.pack(fill="x", padx=16, pady=(2, 10))
        self.connection_frame.configure(height=132)
        self.connection_frame.pack_propagate(False)
        self.connection_frame.grid_columnconfigure((0, 1), weight=1, uniform="connection_info")
        self.connection_frame.grid_rowconfigure(0, weight=1)

        self.apache_info_frame = ctk.CTkFrame(self.connection_frame, corner_radius=10)
        self.apache_info_label = ctk.CTkLabel(self.apache_info_frame, text=self.t("apache_active_info", port=self.apache_port()), font=ctk.CTkFont(weight="bold"))
        self.apache_info_label.pack(anchor="w", padx=14, pady=(12, 6))
        self.apache_info_frame.grid(row=0, column=0, sticky="nsew", padx=(12, 6), pady=12)
        self.open_home_button = ctk.CTkButton(self.apache_info_frame, text=self.t("open_home"), command=self.open_home)
        self.open_home_button.pack(anchor="w", padx=14, pady=(0, 12))

        self.mysql_info_frame = ctk.CTkFrame(self.connection_frame, corner_radius=10)
        self.mysql_info_label = ctk.CTkLabel(self.mysql_info_frame, text="", justify="left", anchor="w")
        self.mysql_info_label.pack(anchor="w", padx=14, pady=(12, 8))
        self.mysql_info_frame.grid(row=0, column=1, sticky="nsew", padx=(6, 12), pady=12)
        self.open_phpmyadmin_button = ctk.CTkButton(
            self.mysql_info_frame,
            text=self.t("open_phpmyadmin"),
            command=self.open_phpmyadmin,
            state="disabled",
        )
        self.open_phpmyadmin_button.pack(anchor="w", padx=14, pady=(0, 12))

        self.log_textbox = ctk.CTkTextbox(self.dashboard_tab, height=180, state="disabled")
        self.log_textbox.pack(fill="both", expand=True, padx=16, pady=(8, 10))

    def _bind_dropdown_open(self, widget) -> None:
        def open_dropdown(_event=None):
            if widget.cget("state") == "disabled":
                return
            if hasattr(widget, "_open_dropdown"):
                widget._open_dropdown()
            elif hasattr(widget, "_open_dropdown_menu"):
                widget._open_dropdown_menu()

        widget.bind("<Button-1>", open_dropdown, add="+")

    def _build_php_tab(self) -> None:
        self.php_settings_panel = PhpSettingsPanel(
            self.php_tab,
            php_ini_getter=self.current_php_ini,
            apache_running_callback=lambda: self.server_manager.is_running("apache"),
            restart_apache_callback=self.restart_apache,
            log_callback=self.log,
            translation_callback=self.t,
        )
        self.php_settings_panel.pack(fill="both", expand=True, padx=16, pady=16)

    def _php_combo_values(self) -> list[str]:
        return [version.label for version in self.php_versions] or [self.t("no_version_found")]

    def _apache_combo_values(self) -> list[str]:
        return [version.label for version in self.apache_versions] or [self.t("no_version_found")]

    def _apply_runtime_state(self) -> None:
        if self.php_version_combobox.get() not in self.php_by_label:
            self.php_version_combobox.set(self.php_versions[0].label if self.php_versions else self.t("no_version_found"))
        if self.apache_version_combobox.get() not in self.apache_by_label:
            self.apache_version_combobox.set(self.apache_versions[0].label if self.apache_versions else self.t("no_version_found"))

        self._update_action_buttons()

        if hasattr(self, "php_settings_panel"):
            self.php_settings_panel.reload()

    def _update_action_buttons(self) -> None:
        apache_ready = bool(self.apache_versions and self.php_versions)
        mysql_ready = self.mysql_path().is_file()

        self.apache_start_button.configure(state="normal" if apache_ready else "disabled")
        self.mysql_start_button.configure(state="normal" if mysql_ready else "disabled")

        if not self.apache_versions:
            self.log(self.t("log_no_apache_versions"))
        if not self.php_versions:
            self.log(self.t("log_no_php_versions"))
        if not mysql_ready:
            self.log(self.t("log_mysql_missing", path=self.mysql_path()))

    def _update_connection_boxes(self) -> None:
        if not hasattr(self, "apache_info_frame"):
            return

        apache_active = self.server_manager.is_running("apache")
        mysql_active = self.server_manager.is_running("mysql")

        if apache_active:
            self.apache_info_label.configure(
                text=self.t("apache_active_info", port=self.apache_port()),
                text_color="#dce8ff",
            )
            self.open_home_button.configure(state="normal")
        else:
            self.apache_info_label.configure(text=self.t("apache_inactive_info"), text_color="#8f98a8")
            self.open_home_button.configure(state="disabled")

        if mysql_active:
            self.mysql_info_label.configure(
                text=self.t("mysql_info", port=self.mysql_port()),
                text_color="#dce8ff",
            )
        else:
            self.mysql_info_label.configure(text=self.t("mysql_inactive_info"), text_color="#8f98a8")

        self.open_phpmyadmin_button.configure(state="normal" if apache_active and mysql_active else "disabled")

    def refresh_runtime_versions(self) -> None:
        self._scan_runtimes()
        self.php_version_combobox.configure(values=self._php_combo_values(), state="readonly" if self.php_versions else "disabled")
        self.apache_version_combobox.configure(values=self._apache_combo_values(), state="readonly" if self.apache_versions else "disabled")
        self._apply_runtime_state()
        self.log(self.t("log_scan_complete"))

    def selected_apache(self) -> RuntimeVersion | None:
        return self.apache_by_label.get(self.apache_version_combobox.get())

    def selected_php(self) -> RuntimeVersion | None:
        return self.php_by_label.get(self.php_version_combobox.get())

    def current_php_ini(self) -> Path | None:
        php = self.selected_php()
        if not php:
            return None

        try:
            return self.server_manager.ensure_php_ini(php.root)
        except Exception as exc:
            self.log(self.t("log_php_ini_unavailable", error=exc))
            return None

    def mysql_path(self) -> Path:
        return resolve_setting_path(self.settings.get("mysql_path", DEFAULT_SETTINGS["mysql_path"])).resolve()

    def document_root_path(self) -> Path:
        return resolve_setting_path(self.settings.get("document_root", DEFAULT_SETTINGS["document_root"])).resolve()

    def apache_port(self) -> int:
        return safe_port(self.settings.get("apache_port", "80"), 80)

    def mysql_port(self) -> int:
        return safe_port(self.settings.get("mysql_port", "3306"), 3306)

    def open_home(self) -> None:
        webbrowser.open(f"http://localhost:{self.apache_port()}")

    def open_phpmyadmin(self) -> None:
        self.configure_phpmyadmin()
        webbrowser.open(f"http://localhost:{self.apache_port()}/phpmyadmin/")

    def configure_phpmyadmin(self) -> None:
        try:
            configure_phpmyadmin(self.document_root_path(), self.log)
        except Exception as exc:
            self.log(self.t("log_phpmyadmin_not_configured", error=exc))

    def toggle_apache(self) -> None:
        apache = self.selected_apache()
        php = self.selected_php()
        if not apache or not apache.executable or not php:
            self.log(self.t("log_apache_php_not_configured_start"))
            return

        self._toggle_server(
            name="apache",
            title="Apache",
            exe_path=apache.executable,
            ports=(self.apache_port(),),
            label=self.apache_status_label,
            button=self.apache_start_button,
            php_dir=php.root,
            document_root=self.document_root_path(),
            apache_port=self.apache_port(),
        )

    def toggle_mysql(self) -> None:
        self._toggle_server(
            name="mysql",
            title="MySQL",
            exe_path=self.mysql_path(),
            ports=(self.mysql_port(),),
            label=self.mysql_status_label,
            button=self.mysql_start_button,
            mysql_port=self.mysql_port(),
        )

    def _toggle_server(
        self,
        name,
        title,
        exe_path,
        ports,
        label,
        button,
        php_dir=None,
        document_root=None,
        apache_port=None,
        mysql_port=None,
    ) -> None:
        button.configure(state="disabled")
        label.configure(text=self.t("status_working", service=title), text_color="#ffb020")
        threading.Thread(
            target=self._toggle_server_worker,
            args=(name, title, exe_path, ports, label, button, php_dir, document_root, apache_port, mysql_port),
            daemon=True,
        ).start()

    def _toggle_server_worker(self, name, title, exe_path, ports, label, button, php_dir, document_root, apache_port, mysql_port) -> None:
        try:
            if self.server_manager.is_running(name):
                self._threadsafe_log(self.t("log_stop_requested", service=title))
                self.server_manager.stop(name)
                self.after(0, self._set_server_status, title, label, button, False)
                return

            self._threadsafe_log(self.t("log_start_requested", service=title, path=exe_path))
            start_kwargs = {
                "name": name,
                "exe_path": exe_path,
                "ports": ports,
            }
            if php_dir:
                start_kwargs["php_dir"] = php_dir
            if document_root:
                start_kwargs["document_root"] = document_root
            if apache_port:
                start_kwargs["apache_port"] = apache_port
            if mysql_port:
                start_kwargs["mysql_port"] = mysql_port

            self.server_manager.start(**start_kwargs)
            self.after(0, self._set_server_status, title, label, button, True)
        except Exception as exc:
            self.after(0, self._set_server_error, title, label, button)
            self._threadsafe_log(str(exc))

    def _set_server_status(self, title, label, button, active: bool) -> None:
        if active:
            label.configure(text=self.t("status_active", service=title), text_color="#2cc985")
            button.configure(text=self.t("stop"), state="normal")
        else:
            label.configure(text=self.t("status_inactive", service=title), text_color="#ff5c5c")
            button.configure(text=self.t("start"), state="normal")
            self._update_action_buttons()

        self._update_connection_boxes()

    def _set_server_error(self, title, label, button) -> None:
        label.configure(text=self.t("status_error", service=title), text_color="#ffb020")
        button.configure(text=self.t("start"), state="normal")
        self._update_action_buttons()
        self._update_connection_boxes()

    def _threadsafe_log(self, message: str) -> None:
        if not self._is_closing:
            self.after(0, self.log, message)

    def log(self, message: str) -> None:
        if self._is_closing or not hasattr(self, "log_textbox"):
            return

        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_textbox.configure(state="normal")
        self.log_textbox.insert("end", f"[{timestamp}] {message}\n")
        self.log_textbox.see("end")
        self.log_textbox.configure(state="disabled")

    def _refresh_server_statuses(self) -> None:
        if self._is_closing:
            return

        self._sync_server_status("apache", "Apache", self.apache_status_label, self.apache_start_button)
        self._sync_server_status("mysql", "MySQL", self.mysql_status_label, self.mysql_start_button)
        self._update_connection_boxes()
        self.after(2000, self._refresh_server_statuses)

    def _sync_server_status(self, name, title, label, button) -> None:
        if button.cget("state") == "disabled":
            return
        self._set_server_status(title, label, button, active=self.server_manager.is_running(name))

    def restart_apache(self) -> None:
        threading.Thread(target=self._restart_apache_worker, daemon=True).start()

    def _restart_apache_worker(self) -> None:
        apache = self.selected_apache()
        php = self.selected_php()
        if not apache or not apache.executable or not php:
            self._threadsafe_log(self.t("log_apache_php_not_configured_restart"))
            return

        try:
            if self.server_manager.is_running("apache"):
                self._threadsafe_log(self.t("log_restart_requested"))
                apache_pid = self.server_manager.get_pid("apache")
                self.server_manager.stop("apache")
                self._wait_for_pid_exit(apache_pid)

            self.server_manager.start(
                name="apache",
                exe_path=apache.executable,
                ports=(self.apache_port(),),
                php_dir=php.root,
                document_root=self.document_root_path(),
                apache_port=self.apache_port(),
            )
            self.after(0, self._set_server_status, "Apache", self.apache_status_label, self.apache_start_button, True)
        except Exception as exc:
            self.after(0, self._set_server_error, "Apache", self.apache_status_label, self.apache_start_button)
            self._threadsafe_log(str(exc))

    def _wait_for_pid_exit(self, pid: int | None) -> None:
        if not pid:
            return

        for _ in range(10):
            if not self.server_manager.is_pid_alive(pid):
                return
            time.sleep(0.2)

    def on_closing(self) -> None:
        if self._is_closing:
            return

        self._is_closing = True
        try:
            self.server_manager.stop_all()
        except Exception as exc:
            print(f"Shutdown cleanup error: {exc}")

        try:
            self.after(300, self.destroy)
        except Exception:
            pass

    def _build_download_tab(self) -> None:
        self.download_tab.grid_columnconfigure((0, 1), weight=1, uniform="download_columns")
        self.download_tab.grid_rowconfigure(0, weight=1)

        self.php_download_panel = self._build_download_panel(
            parent=self.download_tab,
            title=self.t("download_php_title"),
            installed_title=self.t("installed_php_versions"),
            installed_versions=self._php_combo_values(),
            fallback_url="https://windows.php.net/download/",
            fallback_note=(
                "Scarica PHP VS16 x64 Thread Safe. "
                "Scompatta lo ZIP in bin/php/php-X.Y.Z/ e poi premi Riscansiona."
            ),
            sample_versions=("PHP 8.5.x", "PHP 8.4.x", "PHP 8.3.x"),
        )
        self.php_download_panel["frame"].grid(row=0, column=0, sticky="nsew", padx=(16, 8), pady=16)
        self.php_download_panel["verify_button"].configure(command=lambda: self._check_php_updates(self.php_download_panel))

        self.apache_download_panel = self._build_download_panel(
            parent=self.download_tab,
            title=self.t("download_apache_title"),
            installed_title=self.t("installed_apache_versions"),
            installed_versions=self._apache_combo_values(),
            fallback_url="https://www.apachelounge.com/download/",
            fallback_note=(
                "Scarica Apache VS16 x64 da Apache Lounge. "
                "Scompatta lo ZIP in bin/apache/apache-X.Y.Z/ e poi premi Riscansiona."
            ),
            sample_versions=("Apache 2.4.x", "Apache 2.4.x LTS", "Apache 2.4.x Latest"),
        )
        self.apache_download_panel["frame"].grid(row=0, column=1, sticky="nsew", padx=(8, 16), pady=16)
        self.apache_download_panel["verify_button"].configure(command=lambda: self._check_apache_updates(self.apache_download_panel))

    def _build_download_panel(
        self,
        parent,
        title: str,
        installed_title: str,
        installed_versions: list[str],
        fallback_url: str,
        fallback_note: str,
        sample_versions: tuple[str, str, str],
    ) -> dict[str, object]:
        panel = ctk.CTkFrame(parent, corner_radius=14)
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_rowconfigure(2, weight=1)

        title_label = ctk.CTkLabel(panel, text=title, font=ctk.CTkFont(size=18, weight="bold"))
        title_label.grid(row=0, column=0, sticky="w", padx=18, pady=(18, 12))

        installed_label = ctk.CTkLabel(panel, text=installed_title, font=ctk.CTkFont(size=14, weight="bold"))
        installed_label.grid(row=1, column=0, sticky="w", padx=18, pady=(0, 6))

        installed_textbox = ctk.CTkTextbox(panel, height=96, state="normal")
        installed_textbox.grid(row=2, column=0, sticky="nsew", padx=18, pady=(0, 12))
        installed_textbox.insert("end", "\n".join(installed_versions))
        installed_textbox.configure(state="disabled")

        verify_button = ctk.CTkButton(panel, text=self.t("verify_updates"))
        verify_button.grid(row=3, column=0, sticky="ew", padx=18, pady=(0, 12))

        results_frame = ctk.CTkFrame(panel, corner_radius=10)
        results_frame.grid(row=4, column=0, sticky="ew", padx=18, pady=(0, 14))
        results_frame.grid_columnconfigure(0, weight=1)

        placeholder_label = ctk.CTkLabel(
            results_frame,
            text=self.t("download_placeholder"),
            text_color="#8f98a8",
            anchor="w",
        )
        placeholder_label.grid(row=0, column=0, sticky="ew", padx=12, pady=12)

        fallback_frame = ctk.CTkFrame(panel, corner_radius=10, fg_color="transparent")
        fallback_frame.grid(row=5, column=0, sticky="ew", padx=18, pady=(0, 18))
        fallback_frame.grid_columnconfigure(0, weight=1)

        link_button = ctk.CTkButton(
            fallback_frame,
            text=fallback_url,
            fg_color="transparent",
            hover_color=("#d8e8ff", "#1e3550"),
            text_color=("#0a58ca", "#7db7ff"),
            anchor="w",
            command=lambda url=fallback_url: webbrowser.open(url),
        )
        link_button.grid(row=0, column=0, sticky="ew", pady=(0, 4))

        fallback_label = ctk.CTkLabel(
            fallback_frame,
            text=fallback_note,
            wraplength=420,
            justify="left",
            anchor="w",
            text_color="#8f98a8",
        )
        fallback_label.grid(row=1, column=0, sticky="ew")

        panel_data = {
            "frame": panel,
            "installed_textbox": installed_textbox,
            "verify_button": verify_button,
            "results_frame": results_frame,
            "sample_versions": sample_versions,
        }
        verify_button.configure(command=lambda data=panel_data: self._simulate_update_check(data))
        return panel_data

    def _refresh_download_installed_lists(self) -> None:
        if hasattr(self, "php_download_panel"):
            self._set_readonly_textbox(self.php_download_panel["installed_textbox"], "\n".join(self._php_combo_values()))
        if hasattr(self, "apache_download_panel"):
            self._set_readonly_textbox(self.apache_download_panel["installed_textbox"], "\n".join(self._apache_combo_values()))

    def _set_readonly_textbox(self, textbox, text: str) -> None:
        textbox.configure(state="normal")
        textbox.delete("1.0", "end")
        textbox.insert("end", text)
        textbox.configure(state="disabled")

    def _clear_results_frame(self, results_frame) -> None:
        for widget in results_frame.winfo_children():
            widget.destroy()

    def _set_results_message(self, results_frame, message: str, color: str = "#8f98a8") -> None:
        self._clear_results_frame(results_frame)
        label = ctk.CTkLabel(results_frame, text=message, text_color=color, anchor="w", wraplength=420, justify="left")
        label.grid(row=0, column=0, sticky="ew", padx=12, pady=12)

    def _check_php_updates(self, panel_data: dict[str, object]) -> None:
        button = panel_data["verify_button"]
        results_frame = panel_data["results_frame"]
        button.configure(text=self.t("checking"), state="disabled")
        self._set_results_message(results_frame, self.t("connecting_php"), "#ffb020")
        threading.Thread(target=self._check_php_updates_worker, args=(panel_data,), daemon=True).start()

    def _check_php_updates_worker(self, panel_data: dict[str, object]) -> None:
        try:
            packages = fetch_latest_php_packages(limit=3)
            if not packages:
                raise RuntimeError(self.t("no_php_package"))
            self.after(0, self._show_php_update_results, panel_data, packages)
        except Exception as exc:
            self.after(0, self._show_php_update_error, panel_data, str(exc))

    def _show_php_update_error(self, panel_data: dict[str, object], message: str) -> None:
        panel_data["verify_button"].configure(text=self.t("verify_updates"), state="normal")
        self._set_results_message(
            panel_data["results_frame"],
            self.t("online_check_error", error=message),
            "#ff5c5c",
        )

    def _show_php_update_results(self, panel_data: dict[str, object], packages: list[PhpPackage]) -> None:
        button = panel_data["verify_button"]
        results_frame = panel_data["results_frame"]
        self._clear_results_frame(results_frame)
        results_frame.grid_columnconfigure(0, weight=1)

        for index, package in enumerate(packages):
            version_label = ctk.CTkLabel(results_frame, text=f"PHP {package.version}", anchor="w")
            version_label.grid(row=index, column=0, sticky="ew", padx=(12, 8), pady=6)

            install_button = ctk.CTkButton(results_frame, text=self.t("install_version"), width=140)
            install_button.configure(command=lambda pkg=package, data=panel_data, btn=install_button: self._install_php_package(pkg, data, btn))
            install_button.grid(row=index, column=1, sticky="e", padx=(8, 12), pady=6)

        button.configure(text=self.t("verify_updates"), state="normal")

    def _install_php_package(self, package: PhpPackage, panel_data: dict[str, object], install_button) -> None:
        results_frame = panel_data["results_frame"]
        self._set_download_tab_enabled(False)
        install_button.configure(text=self.t("installing"), state="disabled")

        progress_row = len(results_frame.winfo_children()) + 1
        progress_bar = ctk.CTkProgressBar(results_frame)
        progress_bar.set(0)
        progress_bar.grid(row=progress_row, column=0, columnspan=2, sticky="ew", padx=12, pady=(10, 4))

        progress_label = ctk.CTkLabel(results_frame, text=self.t("download_zero"), text_color="#ffb020", anchor="w")
        progress_label.grid(row=progress_row + 1, column=0, columnspan=2, sticky="ew", padx=12, pady=(0, 10))

        threading.Thread(
            target=self._install_php_package_worker,
            args=(package, panel_data, progress_bar, progress_label, install_button),
            daemon=True,
        ).start()

    def _install_php_package_worker(self, package: PhpPackage, panel_data: dict[str, object], progress_bar, progress_label, install_button) -> None:
        def progress(downloaded: int, total: int) -> None:
            if total > 0:
                ratio = min(downloaded / total, 1)
                percent = int(ratio * 100)
                self.after(0, progress_bar.set, ratio)
                self.after(0, lambda: progress_label.configure(text=self.t("download_percent", percent=percent)))
            else:
                mb = downloaded / (1024 * 1024)
                self.after(0, lambda: progress_label.configure(text=self.t("download_mb", mb=mb)))

        try:
            target_dir = download_and_install_php(package, progress)
            self.after(0, self._finish_php_install_success, panel_data, package, target_dir, progress_label, install_button)
        except Exception as exc:
            self.after(0, self._finish_php_install_error, panel_data, str(exc), progress_label, install_button)

    def _finish_php_install_success(self, panel_data: dict[str, object], package: PhpPackage, target_dir: Path, progress_label, install_button) -> None:
        progress_label.configure(text=self.t("install_complete", name=target_dir.name), text_color="#2cc985")
        self._set_download_tab_enabled(True)
        install_button.configure(text=self.t("installed"), state="disabled")
        self.refresh_runtime_versions()
        self.log(self.t("php_installed_log", version=package.version, path=target_dir))
    def _finish_php_install_error(self, panel_data: dict[str, object], message: str, progress_label, install_button) -> None:
        progress_label.configure(text=self.t("install_error", error=message), text_color="#ff5c5c")
        self._set_download_tab_enabled(True)
        install_button.configure(text=self.t("install_version"), state="normal")
    def _check_apache_updates(self, panel_data: dict[str, object]) -> None:
        button = panel_data["verify_button"]
        results_frame = panel_data["results_frame"]
        button.configure(text=self.t("checking"), state="disabled")
        self._set_results_message(results_frame, self.t("connecting_apache"), "#ffb020")
        threading.Thread(target=self._check_apache_updates_worker, args=(panel_data,), daemon=True).start()

    def _check_apache_updates_worker(self, panel_data: dict[str, object]) -> None:
        try:
            packages = fetch_latest_apache_packages(limit=1)
            if not packages:
                raise RuntimeError(self.t("no_apache_package"))
            self.after(0, self._show_apache_update_results, panel_data, packages)
        except Exception as exc:
            self.after(0, self._show_apache_update_error, panel_data, str(exc))

    def _show_apache_update_error(self, panel_data: dict[str, object], message: str) -> None:
        panel_data["verify_button"].configure(text=self.t("verify_updates"), state="normal")
        self._set_results_message(
            panel_data["results_frame"],
            self.t("online_check_error", error=message),
            "#ff5c5c",
        )

    def _show_apache_update_results(self, panel_data: dict[str, object], packages: list[ApachePackage]) -> None:
        button = panel_data["verify_button"]
        results_frame = panel_data["results_frame"]
        self._clear_results_frame(results_frame)
        results_frame.grid_columnconfigure(0, weight=1)

        for index, package in enumerate(packages):
            version_label = ctk.CTkLabel(results_frame, text=f"Apache {package.version}", anchor="w")
            version_label.grid(row=index, column=0, sticky="ew", padx=(12, 8), pady=6)

            install_button = ctk.CTkButton(results_frame, text=self.t("install_version"), width=140)
            install_button.configure(command=lambda pkg=package, data=panel_data, btn=install_button: self._install_apache_package(pkg, data, btn))
            install_button.grid(row=index, column=1, sticky="e", padx=(8, 12), pady=6)

        button.configure(text=self.t("verify_updates"), state="normal")

    def _install_apache_package(self, package: ApachePackage, panel_data: dict[str, object], install_button) -> None:
        results_frame = panel_data["results_frame"]
        self._set_download_tab_enabled(False)
        install_button.configure(text=self.t("installing"), state="disabled")

        progress_row = len(results_frame.winfo_children()) + 1
        progress_bar = ctk.CTkProgressBar(results_frame)
        progress_bar.set(0)
        progress_bar.grid(row=progress_row, column=0, columnspan=2, sticky="ew", padx=12, pady=(10, 4))

        progress_label = ctk.CTkLabel(results_frame, text=self.t("download_zero"), text_color="#ffb020")
        progress_label.grid(row=progress_row + 1, column=0, columnspan=2, sticky="ew", padx=12, pady=(0, 10))

        threading.Thread(
            target=self._install_apache_package_worker,
            args=(package, panel_data, progress_bar, progress_label, install_button),
            daemon=True,
        ).start()

    def _install_apache_package_worker(self, package: ApachePackage, panel_data: dict[str, object], progress_bar, progress_label, install_button) -> None:
        def progress(downloaded: int, total: int) -> None:
            if total > 0:
                ratio = min(downloaded / total, 1)
                percent = int(ratio * 100)
                self.after(0, progress_bar.set, ratio)
                self.after(0, lambda: progress_label.configure(text=self.t("download_percent", percent=percent)))
            else:
                mb = downloaded / (1024 * 1024)
                self.after(0, lambda: progress_label.configure(text=self.t("download_mb", mb=mb)))

        try:
            target_dir = download_and_install_apache(package, progress)
            self.after(0, self._finish_apache_install_success, panel_data, package, target_dir, progress_label, install_button)
        except Exception as exc:
            self.after(0, self._finish_apache_install_error, panel_data, str(exc), progress_label, install_button)

    def _finish_apache_install_success(self, panel_data: dict[str, object], package: ApachePackage, target_dir: Path, progress_label, install_button) -> None:
        progress_label.configure(text=self.t("install_complete", name=target_dir.name), text_color="#2cc985")
        self._set_download_tab_enabled(True)
        install_button.configure(text=self.t("installed"), state="disabled")
        self.refresh_runtime_versions()
        self.log(self.t("apache_installed_log", version=package.version, path=target_dir))

    def _finish_apache_install_error(self, panel_data: dict[str, object], message: str, progress_label, install_button) -> None:
        progress_label.configure(text=self.t("install_error", error=message), text_color="#ff5c5c")
        self._set_download_tab_enabled(True)
        install_button.configure(text=self.t("install_version"), state="normal")
    def _set_download_tab_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for panel_name in ("php_download_panel", "apache_download_panel"):
            if hasattr(self, panel_name):
                self._set_widget_tree_state(getattr(self, panel_name)["frame"], state)

    def _set_widget_tree_state(self, widget, state: str) -> None:
        if isinstance(widget, ctk.CTkButton):
            if state == "normal" and widget.cget("text") in {self.t("install"), self.t("installed")}:
                widget.configure(state="disabled")
            else:
                widget.configure(state=state)
        for child in widget.winfo_children():
            self._set_widget_tree_state(child, state)
    def _simulate_update_check(self, panel_data: dict[str, object]) -> None:
        button = panel_data["verify_button"]
        results_frame = panel_data["results_frame"]
        button.configure(text=self.t("checking"), state="disabled")

        for widget in results_frame.winfo_children():
            widget.destroy()

        loading_label = ctk.CTkLabel(results_frame, text=self.t("loading_packages"), text_color="#ffb020")
        loading_label.grid(row=0, column=0, sticky="w", padx=12, pady=12)

        self.after(1000, lambda data=panel_data: self._show_fake_update_results(data))

    def _show_fake_update_results(self, panel_data: dict[str, object]) -> None:
        button = panel_data["verify_button"]
        results_frame = panel_data["results_frame"]
        sample_versions = panel_data["sample_versions"]

        for widget in results_frame.winfo_children():
            widget.destroy()

        results_frame.grid_columnconfigure(0, weight=1)
        for index, version in enumerate(sample_versions):
            version_label = ctk.CTkLabel(results_frame, text=self.t("version_label", version=version), anchor="w")
            version_label.grid(row=index, column=0, sticky="ew", padx=(12, 8), pady=6)

            install_button = ctk.CTkButton(results_frame, text=self.t("install"), width=96, state="disabled")
            install_button.grid(row=index, column=1, sticky="e", padx=(8, 12), pady=6)

        button.configure(text=self.t("verify_updates"), state="normal")

    def _build_settings_tab(self) -> None:
        panel = ctk.CTkFrame(self.settings_tab, corner_radius=12)
        panel.pack(fill="x", padx=16, pady=16)
        panel.grid_columnconfigure((0, 1), weight=1)

        mysql_label = ctk.CTkLabel(panel, text=self.t("settings_mysql_path"))
        mysql_label.grid(row=0, column=0, columnspan=2, sticky="w", padx=16, pady=(16, 6))

        self.mysql_path_entry = ctk.CTkEntry(panel)
        self.mysql_path_entry.insert(0, str(self.mysql_path()))
        self.mysql_path_entry.grid(row=1, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 16))

        document_root_label = ctk.CTkLabel(panel, text=self.t("settings_document_root"))
        document_root_label.grid(row=2, column=0, columnspan=2, sticky="w", padx=16, pady=(4, 6))

        self.document_root_entry = ctk.CTkEntry(panel)
        self.document_root_entry.insert(0, str(self.document_root_path()))
        self.document_root_entry.grid(row=3, column=0, sticky="ew", padx=(16, 8), pady=(0, 16))

        browse_button = ctk.CTkButton(panel, text=self.t("browse"), width=120, command=self.browse_document_root)
        browse_button.grid(row=3, column=1, sticky="e", padx=(0, 16), pady=(0, 16))

        apache_port_label = ctk.CTkLabel(panel, text=self.t("settings_apache_port"))
        apache_port_label.grid(row=4, column=0, sticky="w", padx=16, pady=(4, 6))

        mysql_port_label = ctk.CTkLabel(panel, text=self.t("settings_mysql_port"))
        mysql_port_label.grid(row=4, column=1, sticky="w", padx=16, pady=(4, 6))

        self.apache_port_entry = ctk.CTkEntry(panel)
        self.apache_port_entry.insert(0, str(self.apache_port()))
        self.apache_port_entry.grid(row=5, column=0, sticky="ew", padx=16, pady=(0, 16))

        self.mysql_port_entry = ctk.CTkEntry(panel)
        self.mysql_port_entry.insert(0, str(self.mysql_port()))
        self.mysql_port_entry.grid(row=5, column=1, sticky="ew", padx=16, pady=(0, 16))

        language_label = ctk.CTkLabel(panel, text=self.t("settings_language"))
        language_label.grid(row=6, column=0, sticky="w", padx=16, pady=(4, 6))

        self.language_option = ctk.CTkOptionMenu(
            panel,
            values=list(LANGUAGE_LABELS.values()),
            command=self.change_language,
        )
        self.language_option.set(self._current_language_label())
        self.language_option.grid(row=7, column=0, sticky="ew", padx=16, pady=(0, 16))

        save_button = ctk.CTkButton(panel, text=self.t("save"), width=120, command=self.save_settings_from_ui)
        save_button.grid(row=8, column=0, sticky="w", padx=16, pady=(0, 16))

        self.settings_status_label = ctk.CTkLabel(panel, text="")
        self.settings_status_label.grid(row=9, column=0, columnspan=2, sticky="w", padx=16, pady=(0, 16))

    def browse_document_root(self) -> None:
        selected_dir = filedialog.askdirectory(
            initialdir=self.document_root_entry.get().strip() or str(self.document_root_path()),
            title=self.t("select_project_folder"),
        )
        if not selected_dir:
            return

        self.document_root_entry.delete(0, "end")
        self.document_root_entry.insert(0, selected_dir)

    def save_settings_from_ui(self) -> None:
        document_root = self.document_root_entry.get().strip() or str(DEFAULT_DOCUMENT_ROOT)
        Path(document_root).mkdir(parents=True, exist_ok=True)

        self.settings = {
            "mysql_path": path_to_setting(self.mysql_path_entry.get().strip()),
            "document_root": path_to_setting(document_root),
            "apache_port": str(safe_port(self.apache_port_entry.get(), 80)),
            "mysql_port": str(safe_port(self.mysql_port_entry.get(), 3306)),
            "lang": language_code_from_label(self.language_option.get()) or self.settings.get("lang", "en"),
        }
        save_settings(self.settings)
        self.apache_port_entry.delete(0, "end")
        self.apache_port_entry.insert(0, self.settings["apache_port"])
        self.mysql_port_entry.delete(0, "end")
        self.mysql_port_entry.insert(0, self.settings["mysql_port"])
        self.settings_status_label.configure(text=self.t("settings_saved"), text_color="#2cc985")
        self.log(self.t("log_settings_saved"))
        self.configure_phpmyadmin()
        self._update_action_buttons()
        self._update_connection_boxes()


def main() -> None:
    app = LocalWAMPApp()
    app.mainloop()


if __name__ == "__main__":
    main()

















