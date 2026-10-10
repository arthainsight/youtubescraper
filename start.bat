@echo off
setlocal
cd /d "%~dp0"
echo === YouTube-linkkien keraaja ===

set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY ( where python >nul 2>&1 && set "PY=python" )
if not defined PY (
  echo VIRHE: Pythonia ei loytynyt. Asenna Python 64-bit osoitteesta python.org
  echo ja rastita asennuksessa "Add Python to PATH". Avaa sitten tama skripti uudelleen.
  goto :fail
)
echo Kaytetaan: %PY%
%PY% --version || goto :fail

set "VPY=.venv\Scripts\python.exe"
if not exist "%VPY%" (
  if exist ".venv" rmdir /s /q ".venv"
  echo Luodaan virtuaaliympariston .venv ...
  %PY% -m venv .venv || goto :fail
)
if not exist "%VPY%" (
  echo VIRHE: .venv:n luonti epaonnistui.
  goto :fail
)
"%VPY%" --version

echo Asennetaan riippuvuudet (ensimmainen kerta kestaa hetken)...
"%VPY%" -m pip install --upgrade pip
"%VPY%" -m pip install -r requirements.txt || goto :fail

echo.
echo Kaynnistetaan... (lopetus: Ctrl+C)
"%VPY%" -m ytlinks.web %*
if errorlevel 1 goto :fail
goto :eof

:fail
echo.
echo ==== KAYNNISTYS EPAONNISTUI ====
echo Kopioi ylla oleva virheilmoitus ja kerro se, niin korjataan.
echo Vihje: jos Python on hyvin uusi (esim. 3.15), asenna rinnalle 3.13, poista
echo kansio .venv ja aja: py -3.13 -m venv .venv
pause
exit /b 1
