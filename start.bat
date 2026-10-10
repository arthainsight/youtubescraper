@echo off
rem Kaynnistaa selainversion Windowsissa. Luo tarvittaessa .venv-ymparison.
cd /d "%~dp0"
if not exist .venv (
  py -3 -m venv .venv || python -m venv .venv
)
call .venv\Scripts\activate.bat
python -m pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
python -m ytlinks.web %*
