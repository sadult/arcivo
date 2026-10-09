# Building Arcivo for Windows

## Prerequisites
- Windows 10/11 x64, **Python 3.14 or newer** (python.org or `winget install Python.Python.3.14`)
- [Inno Setup 6](https://jrsoftware.org/isinfo.php) for the installer (`winget install JRSoftware.InnoSetup`)
- Git (for the build number)

## One command

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build.ps1
```

This creates `.venv-build`, runs the tests, builds the one-folder app with PyInstaller
(`packaging/pyinstaller/arcivo.spec`), assembles the portable ZIP (adds `portable.flag`), compiles the installer
(`packaging/windows/arcivo.iss`) and writes `dist/SHA256SUMS.txt`.

| Output | Description |
|---|---|
| `dist/Arcivo/` | `Arcivo.exe` (console home screen + CLI) and `ArcivoDashboard.exe` (windowed desktop app) sharing one runtime |
| `dist/Arcivo-<ver>-Setup-x64.exe` | per-user installer: no admin rights, Start-menu + optional desktop shortcut, optional PATH entry, uninstaller that asks before removing local data |
| `dist/Arcivo-<ver>-portable-x64.zip` | unzip anywhere; data stays in `ArcivoData\` beside the exe |

Or just double-click `build.bat`.

Flags: `-SkipTests`, `-SkipInstaller`, `-Iscc "C:\path\to\ISCC.exe"`, `-Python "py -3.14"`, `-Build <id>`. Inno Setup is found via PATH, the registry and Program Files; if missing, the installer step is skipped with a warning.

## CI

`.github/workflows/ci.yml` lints, tests on Windows + Ubuntu (Python 3.14, headless Qt) and builds a portable
artifact on `main`. Pushing a tag `vX.Y.Z` runs `.github/workflows/release.yml`, which builds everything on
`windows-latest` and drafts a GitHub release with the installer, ZIP and checksums.

## Code signing (recommended)

Unsigned executables trigger SmartScreen warnings. Sign `dist/Arcivo/*.exe` before running Inno Setup and the
installer afterwards, e.g. `signtool sign /fd sha256 /tr http://timestamp.digicert.com /td sha256 /a <file>`, or
add `SignTool=` to `arcivo.iss`.
