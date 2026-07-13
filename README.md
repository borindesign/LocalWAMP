# LocalPHP Manager

LocalPHP Manager is a portable PHP development environment for Windows.

This repository is intended to contain the public source code for the desktop manager and the packaging scripts. Runtime binaries, private website files, generated builds, and release ZIP files are intentionally kept out of Git.

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

Release ZIP files should be generated locally into `releases/`, then uploaded to the public download channel, such as `localphp.net`, and optionally attached to GitHub Releases. They should not be committed to the repository.
