from __future__ import annotations

import ctypes
import shutil
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from configure_apache_php import DEFAULT_DOCUMENT_ROOT, configure_apache_php
from diagnostics import port_status
from php_ini_config import ensure_php_ini as ensure_configured_php_ini
from runtime_scanner import PHP_ROOT


CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
STILL_ACTIVE = 259
SUPPORTED_EXECUTABLE_SUFFIXES = {".exe", ".bat", ".cmd"}


class ServerManagerError(Exception):
    pass


class PortUnavailableError(ServerManagerError):
    pass


class ServerAlreadyRunningError(ServerManagerError):
    pass


@dataclass(frozen=True)
class ManagedServer:
    name: str
    exe_path: Path
    process: subprocess.Popen
    ports: tuple[int, ...]

    @property
    def pid(self) -> int:
        return int(self.process.pid)


class ServerManager:
    def __init__(self, log_callback: Callable[[str], None] | None = None) -> None:
        self.processes: dict[str, ManagedServer] = {}
        self._lock = threading.RLock()
        self._log_callback = log_callback

    def start(
        self,
        name: str,
        exe_path: str | Path,
        args: Sequence[str] | None = None,
        ports: Sequence[int] | None = None,
        cwd: str | Path | None = None,
        env: Mapping[str, str] | None = None,
        php_dir: str | Path = PHP_ROOT,
        document_root: str | Path = DEFAULT_DOCUMENT_ROOT,
        apache_port: int = 80,
        mysql_port: int = 3306,
    ) -> ManagedServer:
        with self._lock:
            if self.is_running(name):
                raise ServerAlreadyRunningError(f"{name} e gia in esecuzione")

        executable = self._validate_executable(exe_path)
        server_name = name.lower()

        if server_name == "apache":
            php_path = Path(php_dir).resolve()
            self.ensure_php_ini(php_path)
            apache_root = executable.parent.parent.resolve()
            configure_apache_php(
                apache_root / "conf" / "httpd.conf",
                php_path,
                Path(document_root).resolve(),
                apache_root,
                int(apache_port),
            )
            self._log(
                f"Configurazione Apache aggiornata: ServerRoot {apache_root.as_posix()}, PHPIniDir {php_path.as_posix()}, Listen {int(apache_port)}"
            )

        if server_name == "mysql":
            my_ini_path = executable.parent.parent / "my.ini"
            mysql_config = self.configure_mysql(my_ini_path, int(mysql_port))
            self._log(
                "Configurazione MySQL aggiornata: "
                f"my.ini {mysql_config['my_ini']}, "
                f"basedir {mysql_config['basedir']}, "
                f"datadir {mysql_config['datadir']}, "
                f"port = {int(mysql_port)}"
            )

        required_ports = tuple(int(port) for port in (ports or ()))
        self.check_ports(required_ports)
        command = self._build_command(name, executable, args or ())
        process = self._open_process(command, executable, cwd, env)
        server = ManagedServer(name, executable, process, required_ports)

        with self._lock:
            if self.is_running(name):
                self._kill_process_tree(process.pid)
                raise ServerAlreadyRunningError(f"{name} e gia in esecuzione")
            self.processes[name] = server

        self._log(f"{name}: avviato con PID {server.pid}")
        try:
            if server_name == "mysql":
                self._wait_mysql_startup_or_raise(server)
        except Exception:
            self._kill_process_tree(server.pid)
            raise

        self._start_output_readers(server)
        self._start_exit_watcher(server)
        return server

    def stop(self, name: str) -> bool:
        with self._lock:
            server = self.processes.pop(name, None)

        if server is None:
            self._log(f"{name}: stop richiesto, ma nessun processo registrato")
            return True

        if not self.is_pid_alive(server.pid):
            self._log(f"{name}: PID {server.pid} non piu attivo")
            return True

        try:
            subprocess.Popen(
                ["taskkill", "/F", "/T", "/PID", str(server.pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=CREATE_NO_WINDOW,
            )
            self._log(f"{name}: taskkill inviato per PID {server.pid}")
        except Exception as exc:
            self._log(f"{name}: taskkill fallito: {exc}")

        return True

    def stop_all(self) -> None:
        with self._lock:
            names = list(self.processes.keys())

        for name in names:
            self.stop(name)

    def _kill_process_tree(self, pid: int) -> None:
        if not self.is_pid_alive(pid):
            return
        try:
            subprocess.Popen(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=CREATE_NO_WINDOW,
            )
        except Exception as exc:
            self._log(f"taskkill diagnostico fallito per PID {pid}: {exc}")

    def is_running(self, name: str) -> bool:
        with self._lock:
            server = self.processes.get(name)
            if server is None:
                return False

            if server.process.poll() is not None:
                self.processes.pop(name, None)
                return False

            alive = self.is_pid_alive(server.pid)
            if not alive:
                self.processes.pop(name, None)
            return alive

    def get_pid(self, name: str) -> int | None:
        with self._lock:
            server = self.processes.get(name)
            return server.pid if server and self.is_running(name) else None

    def check_ports(self, ports: Sequence[int]) -> dict[int, str]:
        statuses = {int(port): port_status(int(port)) for port in ports}
        busy_ports = {
            port: status
            for port, status in statuses.items()
            if status.lower() != "libera"
        }

        if busy_ports:
            details = ", ".join(
                f"porta {port}: {status}" for port, status in busy_ports.items()
            )
            raise PortUnavailableError(details)

        return statuses

    def ensure_php_ini(self, php_dir: str | Path = PHP_ROOT) -> Path:
        php_ini = ensure_configured_php_ini(php_dir)
        self._log(f"php.ini verificato: extension_dir {((php_ini.parent / 'ext').resolve()).as_posix()}")
        return php_ini

    @staticmethod
    def configure_mysql(my_ini_path: str | Path, mysql_port: int) -> dict[str, Path]:
        path = Path(my_ini_path).resolve()
        mysql_root = path.parent.resolve()
        data_dir = mysql_root / "data"
        path.parent.mkdir(parents=True, exist_ok=True)
        data_dir.mkdir(parents=True, exist_ok=True)
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines() if path.is_file() else []

        lines = ServerManager._set_ini_section_value(lines, "mysqld", "basedir", f'"{mysql_root.as_posix()}"')
        lines = ServerManager._set_ini_section_value(lines, "mysqld", "datadir", f'"{data_dir.resolve().as_posix()}"')
        lines = ServerManager._set_ini_section_value(lines, "mysqld", "port", str(int(mysql_port)))
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return {"my_ini": path, "basedir": mysql_root, "datadir": data_dir.resolve()}

    @staticmethod
    def _set_ini_section_value(lines: list[str], section: str, key: str, value: str) -> list[str]:
        section_header = f"[{section.lower()}]"
        in_section = False
        section_found = False
        key_written = False
        updated_lines: list[str] = []

        for line in lines:
            stripped = line.strip()
            lower = stripped.lower()

            if stripped.startswith("[") and stripped.endswith("]"):
                if in_section and not key_written:
                    updated_lines.append(f"{key} = {value}")
                    key_written = True
                in_section = lower == section_header
                section_found = section_found or in_section
                updated_lines.append(line)
                continue

            if in_section and lower.startswith(f"{key.lower()} ") and "=" in lower:
                if not key_written:
                    updated_lines.append(f"{key} = {value}")
                    key_written = True
                continue

            if in_section and lower.startswith(f"{key.lower()}="):
                if not key_written:
                    updated_lines.append(f"{key} = {value}")
                    key_written = True
                continue

            updated_lines.append(line)

        if section_found and in_section and not key_written:
            updated_lines.append(f"{key} = {value}")

        if not section_found:
            if updated_lines and updated_lines[-1].strip():
                updated_lines.append("")
            updated_lines.extend([f"[{section}]", f"{key} = {value}"])

        return updated_lines

    @staticmethod
    def is_pid_alive(pid: int) -> bool:
        if int(pid) <= 0:
            return False

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not handle:
            return False

        exit_code = ctypes.c_ulong()
        try:
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return False
            return exit_code.value == STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)

    @staticmethod
    def _validate_executable(exe_path: str | Path) -> Path:
        executable = Path(exe_path)

        if executable.suffix.lower() not in SUPPORTED_EXECUTABLE_SUFFIXES:
            raise ValueError("Il percorso deve puntare a un file .exe, .bat o .cmd")

        if not executable.is_file():
            raise FileNotFoundError(executable)

        return executable.resolve()

    @staticmethod
    def _build_command(name: str, executable: Path, args: Sequence[str]) -> list[str]:
        if name.lower() == "mysql":
            defaults_file = executable.parent.parent / "my.ini"
            return [str(executable), f"--defaults-file={defaults_file.as_posix()}", *args]

        if executable.suffix.lower() in {".bat", ".cmd"}:
            return ["cmd.exe", "/c", str(executable), *args]

        return [str(executable), *args]

    def _open_process(
        self,
        command: list[str],
        executable: Path,
        cwd: str | Path | None,
        env: Mapping[str, str] | None,
    ) -> subprocess.Popen:
        try:
            return subprocess.Popen(
                command,
                cwd=str(Path(cwd) if cwd else executable.parent),
                env=dict(env) if env else None,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=CREATE_NO_WINDOW,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
        except OSError as exc:
            raise ServerManagerError(f"Avvio processo fallito: {exc}") from exc

    def _wait_mysql_startup_or_raise(self, server: ManagedServer, timeout_seconds: float = 5.0) -> None:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            exit_code = server.process.poll()
            if exit_code is not None:
                try:
                    stdout, stderr = server.process.communicate(timeout=1)
                except subprocess.TimeoutExpired:
                    server.process.kill()
                    stdout, stderr = server.process.communicate(timeout=1)

                details = "\n".join(part.strip() for part in (stderr, stdout) if part and part.strip())
                with self._lock:
                    current = self.processes.get(server.name)
                    if current and current.pid == server.pid:
                        self.processes.pop(server.name, None)
                raise ServerManagerError(
                    f"MySQL non avviato entro {timeout_seconds:.0f}s "
                    f"(exit code {exit_code}). Dettagli: {details or 'nessun output da mysqld.exe'}"
                )

            if server.ports and self._ports_are_active(server.ports):
                self._log(f"MySQL: porta attiva rilevata ({', '.join(str(port) for port in server.ports)})")
                return

            time.sleep(0.25)

        if server.ports:
            self._log(
                "MySQL: processo vivo dopo 5s, ma porta non ancora rilevata; "
                "la UI e stata sbloccata e gli errori stderr continueranno nei log"
            )
        else:
            self._log(f"MySQL: nessun errore di avvio rilevato nei primi {timeout_seconds:.0f}s")

    @staticmethod
    def _ports_are_active(ports: Sequence[int]) -> bool:
        return any(port_status(int(port)).lower() != "libera" for port in ports)

    def _start_output_readers(self, server: ManagedServer) -> None:
        for stream_name, stream in (("stdout", server.process.stdout), ("stderr", server.process.stderr)):
            if stream is None:
                continue

            threading.Thread(
                target=self._read_process_output,
                args=(server.name, stream_name, stream),
                daemon=True,
            ).start()

    def _read_process_output(self, name: str, stream_name: str, stream) -> None:
        try:
            for line in iter(stream.readline, ""):
                line = line.rstrip()
                if line:
                    self._log(f"{name} {stream_name}: {line}")
        finally:
            stream.close()

    def _start_exit_watcher(self, server: ManagedServer) -> None:
        threading.Thread(target=self._watch_process_exit, args=(server,), daemon=True).start()

    def _watch_process_exit(self, server: ManagedServer) -> None:
        exit_code = server.process.wait()
        self._log(f"{server.name}: processo terminato con codice {exit_code}")

        with self._lock:
            current = self.processes.get(server.name)
            if current and current.pid == server.pid:
                self.processes.pop(server.name, None)

    def _log(self, message: str) -> None:
        if self._log_callback:
            self._log_callback(message)



