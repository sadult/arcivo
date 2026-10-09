@echo off
setlocal EnableExtensions
title Arcivo build
cd /d "%~dp0"

echo.
echo  ==========================================
echo    Arcivo - Windows build (exe + installer)
echo  ==========================================
echo.

if not exist "packaging\pyinstaller\arcivo.spec" (
  echo [X] Put build.bat in the Arcivo project folder ^(next to pyproject.toml^) and run it again.
  goto :fail
)

rem ---- find Python 3.14 or newer ---------------------------------------------
set "PYCMD="
call :trypy "py -3.14"
call :trypy "py -3"
call :trypy "py"
call :trypy "python"
call :trypy "python3"
if not defined PYCMD (
  echo [X] Python 3.14 or newer was not found.
  echo     Install it from https://www.python.org/downloads/  ^(tick "Add python.exe to PATH"^)
  echo     or run:  winget install Python.Python.3.14
  goto :fail
)
for /f "delims=" %%V in ('%PYCMD% -c "import sys; print(sys.version.split()[0])"') do set "PYVER=%%V"
echo [OK] Python %PYVER%  ^(%PYCMD%^)

rem ---- Inno Setup: build.ps1 searches PATH, the registry and Program Files ------
rem      If it is installed somewhere unusual, set ISCC_PATH below, e.g.
rem      set "ISCC_PATH=D:\Tools\Inno Setup 6\ISCC.exe"
set "ISCC_PATH="
set "ISCC_ARG="
if defined ISCC_PATH set ISCC_ARG=-Iscc "%ISCC_PATH%"

rem ---- build id (works without git) ------------------------------------------
set "BUILDID=local"
for /f %%G in ('git rev-parse --short HEAD 2^>nul') do set "BUILDID=%%G"

rem ---- tests are skipped by default; use "build.bat test" to run them --------
set "TEST_FLAG=-SkipTests"
if /i "%~1"=="test" set "TEST_FLAG="

echo.
echo Building... the first run downloads dependencies and takes a few minutes.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\build.ps1" -Python "%PYCMD%" -Build "%BUILDID%" %TEST_FLAG% %ISCC_ARG%
if errorlevel 1 goto :fail

echo.
echo  ==========================================
echo    Done!  Output folder: dist\
echo      dist\Arcivo\Arcivo.exe            console home screen
echo      dist\Arcivo\ArcivoDashboard.exe   desktop app
echo      dist\Arcivo-*-portable-x64.zip    portable
if exist "dist\Arcivo-*-Setup-x64.exe" echo      dist\Arcivo-*-Setup-x64.exe       installer
echo  ==========================================
start "" explorer "%~dp0dist"
echo.
pause
exit /b 0

:trypy
if defined PYCMD exit /b 0
%~1 -c "import sys; sys.exit(0 if sys.version_info >= (3, 14) else 1)" >nul 2>&1
if not errorlevel 1 set "PYCMD=%~1"
exit /b 0

:fail
echo.
echo [X] Build failed. Scroll up to see the error.
echo.
pause
exit /b 1
