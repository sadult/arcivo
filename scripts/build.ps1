<#
.SYNOPSIS
  Build Arcivo for Windows: PyInstaller app folder, Inno Setup installer and portable ZIP.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\build.ps1            # everything
  powershell -ExecutionPolicy Bypass -File scripts\build.ps1 -SkipInstaller -SkipTests

  Outputs (in .\dist):
    Arcivo\                         one-folder app (Arcivo.exe console + ArcivoDashboard.exe desktop app)
    Arcivo-<ver>-Setup-x64.exe      per-user installer (needs Inno Setup 6+: winget install JRSoftware.InnoSetup)
    Arcivo-<ver>-portable-x64.zip   portable build (data kept next to the exe in ArcivoData\)
    SHA256SUMS.txt
#>
param(
  [string]$Python = "py -3.14",
  [switch]$SkipTests,
  [switch]$SkipInstaller,
  [string]$Iscc = "",
  [string]$Build = ""
)
$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

function Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }

$Version = (Select-String -Path "src\arcivo\__version__.py" -Pattern '__version__ = "([^"]+)"').Matches[0].Groups[1].Value
if (-not $Build) {
  try { $Build = (git rev-parse --short HEAD 2>$null) } catch { $Build = "" }
  if (-not $Build) { $Build = "local" }
}

function Find-Iscc([string]$hint) {
  $candidates = New-Object System.Collections.Generic.List[string]
  if ($hint) { $candidates.Add($hint) }
  if ($env:ARCIVO_ISCC) { $candidates.Add($env:ARCIVO_ISCC) }
  $cmd = Get-Command iscc.exe -ErrorAction SilentlyContinue
  if ($cmd) { $candidates.Add($cmd.Source) }
  # Registry: Inno Setup registers an uninstall entry ("Inno Setup 6_is1", "Inno Setup 7_is1", ...)
  $keys = @("HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*",
            "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*",
            "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*")
  foreach ($k in $keys) {
    Get-ItemProperty $k -ErrorAction SilentlyContinue |
      Where-Object { $_.PSChildName -like "Inno Setup*" -or $_.DisplayName -like "Inno Setup*" } |
      ForEach-Object {
        if ($_.InstallLocation) { $candidates.Add((Join-Path $_.InstallLocation "ISCC.exe")) }
        if ($_.DisplayIcon) {
          $icon = ($_.DisplayIcon -replace '"', '') -replace ',.*$', ''
          $candidates.Add((Join-Path (Split-Path $icon) "ISCC.exe"))
        }
      }
  }
  foreach ($base in @(${env:ProgramFiles(x86)}, $env:ProgramFiles, $env:ProgramW6432, (Join-Path $env:LOCALAPPDATA "Programs"))) {
    if (-not $base) { continue }
    Get-ChildItem -Path $base -Directory -Filter "Inno Setup*" -ErrorAction SilentlyContinue |
      Sort-Object Name -Descending | ForEach-Object { $candidates.Add((Join-Path $_.FullName "ISCC.exe")) }
  }
  foreach ($c in $candidates) { if ($c -and (Test-Path -LiteralPath $c)) { return (Resolve-Path -LiteralPath $c).Path } }
  return $null
}
Write-Host "Arcivo $Version (build $Build)"

Step "Creating virtual environment"
$Py = Join-Path $Root ".venv-build\Scripts\python.exe"
if (Test-Path $Py) {
  & $Py -c "import sys; sys.exit(0 if sys.version_info >= (3, 14) else 1)"
  if ($LASTEXITCODE -ne 0) { Write-Host "Recreating .venv-build (it was made with an older Python)"; Remove-Item ".venv-build" -Recurse -Force }
}
if (-not (Test-Path $Py)) { Invoke-Expression "$Python -m venv .venv-build" }
if (-not (Test-Path $Py)) { throw "Could not create the virtual environment with '$Python'" }
& $Py -c "import sys; print('Python', sys.version.split()[0]); sys.exit(0 if sys.version_info >= (3, 14) else 1)"
if ($LASTEXITCODE -ne 0) { throw "Arcivo needs Python 3.14 or newer (got an older interpreter from '$Python')" }
& $Py -m pip install --upgrade pip wheel | Out-Null
& $Py -m pip install -r requirements.txt -r requirements-dev.txt
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }
& $Py -m pip install -e . --no-deps
if ($LASTEXITCODE -ne 0) { throw "pip install -e . failed" }

if (-not $SkipTests) {
  Step "Running tests"
  $env:QT_QPA_PLATFORM = "offscreen"
  & $Py -m pytest -q
  if ($LASTEXITCODE -ne 0) { throw "Tests failed" }
  Remove-Item Env:QT_QPA_PLATFORM
}

Step "Stamping build number and version resource"
$verFile = "src\arcivo\__version__.py"
$original = Get-Content $verFile -Raw
(Get-Content $verFile -Raw) -replace 'BUILD = "dev"', "BUILD = `"$Build`"" | Set-Content $verFile -NoNewline
$parts = $Version.Split(".")
$template = (Get-Content "packaging\pyinstaller\version_info.template.txt" -Raw).
  Replace("{MAJOR}", $parts[0]).Replace("{MINOR}", $parts[1]).Replace("{PATCH}", ($parts[2] -replace '\D.*$', '')).
  Replace("{VERSION}", $Version)
$template.Replace("{INTERNAL}", "Arcivo").Replace("{DESCRIPTION}", "Arcivo - console home screen and command line") |
  Set-Content "packaging\pyinstaller\version_info_console.txt" -Encoding UTF8
$template.Replace("{INTERNAL}", "ArcivoDashboard").Replace("{DESCRIPTION}", "Arcivo Dashboard - Saved Messages archive manager") |
  Set-Content "packaging\pyinstaller\version_info_gui.txt" -Encoding UTF8

try {
  Step "PyInstaller"
  & $Py -m PyInstaller packaging\pyinstaller\arcivo.spec --noconfirm --clean --distpath dist --workpath build\pyinstaller
  if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }
} finally {
  Set-Content $verFile $original -NoNewline
}

Step "Smoke-testing the bundle"
& "dist\Arcivo\Arcivo.exe" --version
if ($LASTEXITCODE -ne 0) { throw "Arcivo.exe did not start" }
& "dist\Arcivo\Arcivo.exe" --demo status | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Arcivo.exe --demo status failed" }
if (-not (Test-Path "dist\Arcivo\ArcivoDashboard.exe")) { throw "ArcivoDashboard.exe is missing" }

Step "Portable ZIP"
$portableDir = "build\portable\Arcivo"
if (Test-Path "build\portable") { Remove-Item "build\portable" -Recurse -Force }
New-Item -ItemType Directory -Force -Path $portableDir | Out-Null
Copy-Item "dist\Arcivo\*" $portableDir -Recurse
Set-Content (Join-Path $portableDir "portable.flag") "Arcivo portable mode: settings, index and session live in .\ArcivoData next to the executables."
Copy-Item "packaging\windows\README-portable.txt" (Join-Path $portableDir "README.txt")
$zip = "dist\Arcivo-$Version-portable-x64.zip"
if (Test-Path $zip) { Remove-Item $zip }
Compress-Archive -Path "build\portable\Arcivo" -DestinationPath $zip -CompressionLevel Optimal

if (-not $SkipInstaller) {
  Step "Inno Setup installer"
  $isccPath = Find-Iscc $Iscc
  if (-not $isccPath) {
    Write-Warning "Inno Setup (ISCC.exe) not found - skipping the installer. Install it (winget install JRSoftware.InnoSetup) or pass -Iscc 'C:\path\to\ISCC.exe'."
  } else {
    Write-Host "Using $isccPath"
    & $isccPath "/DAppVersion=$Version" "/DSourceDir=$Root\dist\Arcivo" "packaging\windows\arcivo.iss"
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }
  }
}

Step "Checksums"
Get-ChildItem dist -File | Where-Object { $_.Extension -in ".exe", ".zip" } | ForEach-Object {
  "{0}  {1}" -f (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower(), $_.Name
} | Set-Content "dist\SHA256SUMS.txt"
Get-Content "dist\SHA256SUMS.txt"
Write-Host "`nDone. Artifacts are in .\dist" -ForegroundColor Green
