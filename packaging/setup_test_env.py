from pathlib import Path
import sys

APP_DIR = Path(__file__).resolve().parent.parent / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from app_paths import BASE_DIR


DUMMY_SERVERS = {
    BASE_DIR / "bin" / "apache" / "httpd.bat": "Apache",
    BASE_DIR / "bin" / "mysql" / "mysqld.bat": "MySQL",
}


def create_dummy_server(path: Path, title: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "@echo off",
                f"title LocalPHP Dummy {title}",
                "timeout /t 100 /nobreak > nul",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> None:
    for path, title in DUMMY_SERVERS.items():
        create_dummy_server(path, title)
        print(f"Creato: {path}")


if __name__ == "__main__":
    main()
