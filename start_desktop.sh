#!/usr/bin/env bash
# Käynnistää sovelluksen Linuxilla ja macOS:llä. Luo tarvittaessa .venv-ympäristön.
set -e
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
. .venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements-desktop.txt
exec python -m ytlinks
