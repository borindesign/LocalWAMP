# LocalWAMP

LocalWAMP is a portable Windows development environment with Apache, MySQL and PHP, previously named LocalPHP Manager.

It is built for developers who want a simple local PHP stack with Apache, MySQL, phpMyAdmin, and PHP management on Windows.

Live site: [localphp.net](https://localphp.net)

Current release: [LocalWAMP v1.3.0](https://github.com/borindesign/LocalPHP/releases/tag/v1.3.0). The repository and website URLs retain their existing addresses.

This repository contains the public source code for the desktop manager and the packaging scripts. Runtime binaries, private website files, generated builds, and release ZIP files are intentionally kept out of Git.

## Local Layout

- `app/` - Python source code for the LocalWAMP desktop app.
- `assets/` - supplied SVG logo and generated PNG/Windows ICO assets.
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

New packages use `LocalWAMP-v<version>.zip` and contain a `LocalWAMP/` folder with `LocalWAMP.exe`. Historical LocalPHP packages keep their original filenames.

Release ZIP files are generated locally in `releases/` and published through the download channel, such as `localphp.net`, and as GitHub Releases.

## Build

Use Python 3.11+ on Windows, with Tkinter and these development/build dependencies:

```powershell
python -m pip install customtkinter pillow pyinstaller
python packaging\build.py
```

The manager is generated as `dist/LocalWAMP/LocalWAMP.exe`, with its Python/GUI dependencies and icon in `_internal/`, and translations in `system/languages/`. This command does not bundle Apache, PHP, MySQL or phpMyAdmin. For a complete portable ZIP, reuse the runtimes from a previously distributed release:

```powershell
python packaging\build.py --runtime-archive releases\LocalPHP-Manager-v1.2.0.zip
```

This creates `releases/LocalWAMP-v1.3.0.zip`. Only `bin/` and `system/phpmyadmin/` are reused; the old executable and Python bundle are excluded. Use an archive intended for distribution, not a personal installation containing user databases. Build output folders are disposable development artifacts; keep working installations elsewhere.

The original logo is `assets/localwamp.svg`. Generated assets are checked in, so normal builds require no SVG conversion tools. To regenerate them, install the build-only Node.js dependency `sharp` and run `node packaging/generate_icons.cjs`. The script creates a transparent 512 px PNG and an ICO with 16, 24, 32, 48, 64, 128 and 256 px images. If `website/` exists, its logo and favicon are also updated. Update `packaging/build.py` and `packaging/version_info.txt` together when changing versions.

## Updating an existing installation

Close the manager and back up projects and MySQL data. Replace the manager executable, `_internal/` and `system/languages/`, then remove `LocalPHP-Manager.exe`. Preserve `settings.json`, `bin/`, `system/phpmyadmin/` and project folders; do not overwrite these with the full release template. Launch `LocalWAMP.exe` from the same folder. Legacy Apache markers are migrated on the next configuration update.

The app runs without Python installed on the target PC. Runtime binaries require a compatible Windows 10/11 x64 environment and their native dependencies. No workspace folder, domain or repository rename is required.

## Validation

Run `python -m unittest discover -s tests -v`. Also smoke-test source and packaged app, check Windows icons/file properties, and start/stop Apache and MySQL in an isolated portable copy. The local PHP website is maintained separately because `website/` is excluded from public Git.
