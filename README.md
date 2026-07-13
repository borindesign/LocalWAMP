# LocalPHP Manager

LocalPHP Manager is a portable PHP development environment for Windows.

It is built for developers who want a simple local PHP stack with Apache, MySQL, phpMyAdmin, and PHP management on Windows.

Live site: [localphp.net](https://localphp.net)

Current release: [v1.1.0](https://github.com/borindesign/LocalPHP/releases/tag/v1.1.0)

This repository contains the public source code for the desktop manager and the packaging scripts. Runtime binaries, private website files, generated builds, and release ZIP files are intentionally kept out of Git.

## Local Layout

- `app/` - Python source code for the LocalPHP Manager desktop app.
- `packaging/` - build/setup scripts and the PyInstaller spec.
- `docs/` - project documentation, screenshots, notes, and roadmap material.
- `releases/` - local-only release ZIPs generated for distribution. ZIP files are ignored by Git.

## Private/Local-Only Folders

The following folders may exist locally but are not part of the public repository:

- `website/` - private landing/download website.
- `bin/` - local Apache, PHP, and MySQL runtimes.
- `system/phpmyadmin/` - bundled phpMyAdmin runtime dependency.
- `build/` and `dist/` - generated build output.
- `venv/`, `tmp/`, `settings.json` - local development/runtime state.

## Development

Run the app from the project root with:

```powershell
python app\main.py
```

In development, the app resolves the project root as its base directory. In a frozen build, it resolves the executable folder as its base directory so the portable package keeps working from its extracted location.

## Releases

Release ZIP files are generated locally in `releases/` and published through the download channel, such as `localphp.net`, and as GitHub Releases.
