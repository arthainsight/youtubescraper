@echo off
cd /d "%~dp0"
if not exist .venv py -3 -m venv .venv
call .venv\Scripts\activate.bat
pip install --quiet -r requirements-dev.txt
pyinstaller --noconfirm --windowed --name YouTubeLinkkienKeraaja --collect-all yt_dlp --paths . ytlinks_entry.py
echo Valmis: dist\YouTubeLinkkienKeraaja\
