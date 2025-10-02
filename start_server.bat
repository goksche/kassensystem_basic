@echo off
setlocal ENABLEDELAYEDEXPANSION
title Kassensystem starten

set "BASE=%~dp0"
set "VENV=%BASE%venv"
set "PYVENV=%VENV%\Scripts\python.exe"
set "PYDIR=%BASE%py"
set "PYEMB=%PYDIR%\python.exe"

set "PYEXE="
for /f "usebackq tokens=*" %%P in (`py -3 -c "import sys; print(sys.executable)" 2^>nul`) do set "PYEXE=%%P"
if not defined PYEXE for /f "usebackq tokens=*" %%P in (`python -c "import sys; print(sys.executable)" 2^>nul`) do set "PYEXE=%%P"
if not defined PYEXE for /f "usebackq tokens=*" %%P in (`python3 -c "import sys; print(sys.executable)" 2^>nul`) do set "PYEXE=%%P"
if not defined PYEXE if exist "%PYEMB%" set "PYEXE=%PYEMB%"

if not defined PYEXE (
  echo [i] Kein Python gefunden. Lade portable Python ...
  set "URL=https://www.python.org/ftp/python/3.13.7/python-3.13.7-embed-amd64.zip"
  set "ZIP=%BASE%py-embed.zip"
  if not exist "%PYDIR%" mkdir "%PYDIR%"
  powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Invoke-WebRequest -Uri '%URL%' -OutFile '%ZIP%' -UseBasicParsing } catch { exit 1 }"
  if not exist "%ZIP%" (
    echo [!] Download fehlgeschlagen (kein Internet/Proxy?). Installiere Python 3.x manuell ODER installiere in schreibbaren Ordner.
    pause & exit /b 1
  )
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -LiteralPath '%ZIP%' -DestinationPath '%PYDIR%' -Force"
  del /q "%ZIP%" >nul 2>&1
  for %%F in ("%PYDIR%\python3*.?_pth") do (
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
      "$p='%%~fF'; $t=Get-Content $p; $t=$t -replace '^\s*#\s*import\s+site','import site'; Set-Content -Path $p -Value $t -Encoding ASCII"
  )
  if not exist "%PYEMB%" ( echo [!] Portable Python konnte nicht eingerichtet werden. & pause & exit /b 1 )
  set "PYEXE=%PYEMB%"
)

echo [i] Verwende Python: %PYEXE%

if not exist "%PYVENV%" (
  echo [i] Erstelle virtuelle Umgebung ...
  "%PYEXE%" -m venv "%VENV%"
  if not exist "%PYVENV%" (
    echo [!] venv konnte nicht angelegt werden. Wenn der Ordner unter "C:\Program Files" liegt:
    echo     - Starter einmal "Als Administrator ausfuehren" ODER in z.B. C:\Kassensystem installieren.
    pause & exit /b 1
  )
  echo [OK] venv erstellt.
)

if exist "%BASE%requirements.txt" (
  echo [i] Installiere Abhaengigkeiten ...
  "%PYVENV%" -m pip install --upgrade pip
  "%PYVENV%" -m pip install -r "%BASE%requirements.txt"
)

cd /d "%BASE%"
call "%VENV%\Scripts\activate.bat"
"%PYVENV%" -m uvicorn main:app --host 127.0.0.1 --port 8000
endlocal
