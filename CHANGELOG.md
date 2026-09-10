# Changelog

## v1.2.0

- Fixed native PHP extension loading when PHP runs through Apache as `apache2handler`.
- Apache now receives a process-local PATH containing the selected PHP directory and Apache `bin` directory.
- Runtime PATH values are rebuilt on every start and restart so PHP and Apache version changes take effect immediately.
- Added focused tests for Apache environment construction and runtime version changes.
- Fixed the PyInstaller project-root resolution used by the portable build.

## v1.1.0

- Current public release package.
- Portable Windows PHP environment with Apache, MySQL, phpMyAdmin, and PHP runtime management.
