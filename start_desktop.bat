@echo off
rem Kaynnistaa sovelluksen Windowsissa. Luo tarvittaessa .venv-ymparison.
cd /d "%~dp0"
if not exist .venv (
  py -3 -m venv .venv || python -m venv .venv
)
call .venv\Scripts\activate.bat
python -m pip install --quiet --upgrade pip
pip install --quiet -r requirements-desktop.txt
python -m ytlinks
