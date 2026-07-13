from __future__ import annotations

from pathlib import Path

from app_paths import BASE_DIR


DEFAULT_APACHE_CONF = BASE_DIR / "bin" / "apache" / "conf" / "httpd.conf"
DEFAULT_APACHE_ROOT = BASE_DIR / "bin" / "apache"
DEFAULT_PHP_DIR = BASE_DIR / "bin" / "php"
DEFAULT_DOCUMENT_ROOT = BASE_DIR / "www"
PHP_CONFIG_MARKER_START = "# LocalPHP PHP configuration start"
PHP_CONFIG_MARKER_END = "# LocalPHP PHP configuration end"
DOCROOT_MARKER_START = "# LocalPHP DocumentRoot start"
DOCROOT_MARKER_END = "# LocalPHP DocumentRoot end"
PHPMYADMIN_MARKER_START = "# LocalPHP phpMyAdmin start"
PHPMYADMIN_MARKER_END = "# LocalPHP phpMyAdmin end"
DIRECTORY_INDEX_MARKER_START = "# LocalPHP DirectoryIndex start"
DIRECTORY_INDEX_MARKER_END = "# LocalPHP DirectoryIndex end"
DIRECTORY_INDEX_LINE = "DirectoryIndex index.php index.html index.htm"
PHP_COMPATIBILITY_ERROR = (
    "Versione PHP non compatibile con Apache (manca php8apache2_4.dll). "
    "Scarica la versione Thread Safe"
)


class ApachePhpConfigurationError(Exception):
    pass


def configure_apache_php(
    httpd_conf_path: str | Path = DEFAULT_APACHE_CONF,
    php_dir: str | Path = DEFAULT_PHP_DIR,
    document_root: str | Path = DEFAULT_DOCUMENT_ROOT,
    apache_root: str | Path | None = None,
    apache_port: int = 80,
) -> None:
    httpd_conf = Path(httpd_conf_path).resolve()
    php_path = Path(php_dir).resolve()
    document_root_path = Path(document_root).resolve()
    apache_root_path = Path(apache_root).resolve() if apache_root else httpd_conf.parent.parent.resolve()
    php_module = find_php_apache_module(php_path)
    php_ini = php_path / "php.ini"
    php_ini_development = php_path / "php.ini-development"

    if not httpd_conf.is_file():
        raise FileNotFoundError(httpd_conf)

    if not php_ini.is_file():
        if php_ini_development.is_file():
            raise ApachePhpConfigurationError(
                f"php.ini mancante: copia {php_ini_development} in {php_ini}"
            )
        raise FileNotFoundError(php_ini)

    document_root_path.mkdir(parents=True, exist_ok=True)

    php_block = "\n".join(
        [
            PHP_CONFIG_MARKER_START,
            f'LoadModule php_module "{php_module.as_posix()}"',
            f'PHPIniDir "{php_path.as_posix()}"',
            "AddHandler application/x-httpd-php .php",
            PHP_CONFIG_MARKER_END,
        ]
    )

    docroot_block = "\n".join(
        [
            DOCROOT_MARKER_START,
            f'DocumentRoot "{document_root_path.as_posix()}"',
            f'<Directory "{document_root_path.as_posix()}">',
            "    Options Indexes FollowSymLinks",
            "    AllowOverride All",
            "    Require all granted",
            "</Directory>",
            DOCROOT_MARKER_END,
        ]
    )

    directory_index_block = "\n".join(
        [
            DIRECTORY_INDEX_MARKER_START,
            DIRECTORY_INDEX_LINE,
            DIRECTORY_INDEX_MARKER_END,
        ]
    )

    content = httpd_conf.read_text(encoding="utf-8", errors="ignore")
    content = remove_marked_block(content, PHP_CONFIG_MARKER_START, PHP_CONFIG_MARKER_END)
    content = remove_marked_block(content, DOCROOT_MARKER_START, DOCROOT_MARKER_END)
    content = remove_marked_block(content, PHPMYADMIN_MARKER_START, PHPMYADMIN_MARKER_END)
    content = remove_marked_block(content, DIRECTORY_INDEX_MARKER_START, DIRECTORY_INDEX_MARKER_END)
    content = set_server_root(content, apache_root_path)
    content = set_listen_port(content, apache_port)
    content = remove_existing_php_directives(content)
    content = remove_existing_document_root_directives(content)
    content = remove_existing_phpmyadmin_directives(content)
    content = remove_existing_directory_index_directives(content)
    content = (
        content.rstrip()
        + "\n\n"
        + docroot_block
        + "\n\n"
        + directory_index_block
        + "\n\n"
        + php_block
        + "\n"
    )
    httpd_conf.write_text(content, encoding="utf-8")


def find_php_apache_module(php_dir: Path) -> Path:
    matches = sorted(php_dir.rglob("php8apache2_4.dll"), key=lambda path: len(path.parts))
    if not matches:
        raise ApachePhpConfigurationError(PHP_COMPATIBILITY_ERROR)
    return matches[0].resolve()


def set_server_root(content: str, apache_root: Path) -> str:
    server_root_line = f'ServerRoot "{apache_root.as_posix()}"'
    lines = content.splitlines()

    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.lower().startswith("serverroot ") and not stripped.startswith("#"):
            lines[index] = server_root_line
            return "\n".join(lines)

    return server_root_line + "\n" + content


def set_listen_port(content: str, apache_port: int) -> str:
    listen_line = f"Listen {int(apache_port)}"
    lines = content.splitlines()

    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.lower().startswith("listen ") and not stripped.startswith("#"):
            lines[index] = listen_line
            return "\n".join(lines)

    return listen_line + "\n" + content


def remove_existing_php_directives(content: str) -> str:
    blocked_directives = (
        "LoadModule php_module",
        "PHPIniDir",
        "AddHandler application/x-httpd-php .php",
    )
    return "\n".join(
        line
        for line in content.splitlines()
        if not any(directive in line for directive in blocked_directives)
    )


def remove_existing_document_root_directives(content: str) -> str:
    cleaned_lines: list[str] = []
    skipping_directory = False

    for line in content.splitlines():
        stripped = line.strip()
        lower = stripped.lower()

        if skipping_directory:
            if lower.startswith("</directory"):
                skipping_directory = False
            continue

        if lower.startswith("documentroot "):
            continue

        if lower.startswith("<directory") and ("htdocs" in lower or "/www" in lower or "\\www" in lower):
            skipping_directory = True
            continue

        cleaned_lines.append(line)

    return "\n".join(cleaned_lines)


def remove_existing_phpmyadmin_directives(content: str) -> str:
    cleaned_lines: list[str] = []
    skipping_directory = False

    for line in content.splitlines():
        stripped = line.strip()
        lower = stripped.lower()

        if skipping_directory:
            if lower.startswith("</directory"):
                skipping_directory = False
            continue

        if lower.startswith("alias /phpmyadmin"):
            continue

        if lower.startswith("<directory") and "phpmyadmin" in lower:
            skipping_directory = True
            continue

        cleaned_lines.append(line)

    return "\n".join(cleaned_lines)


def remove_existing_directory_index_directives(content: str) -> str:
    return "\n".join(
        line
        for line in content.splitlines()
        if not line.strip().lower().startswith("directoryindex ")
    )


def remove_marked_block(content: str, marker_start: str, marker_end: str) -> str:
    start = content.find(marker_start)
    end = content.find(marker_end)

    if start == -1 or end == -1 or end < start:
        return content

    end += len(marker_end)
    return content[:start].rstrip() + "\n" + content[end:].lstrip()


if __name__ == "__main__":
    configure_apache_php()
    print(f"Configurazione PHP aggiornata in: {DEFAULT_APACHE_CONF}")

