#!/usr/bin/env bash
# Rakentaa itsenäisen ohjelman (dist/YouTubeLinkkienKeraaja) PyInstallerilla. Toimii vain
# siinä käyttöjärjestelmässä, jolla ajetaan (ei ristiinkäännöstä).
set -e
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
. .venv/bin/activate
pip install --quiet -r requirements-dev.txt
pyinstaller --noconfirm --windowed --name YouTubeLinkkienKeraaja \
  --collect-all yt_dlp --paths . ytlinks_entry.py
echo "Valmis: dist/YouTubeLinkkienKeraaja/"
