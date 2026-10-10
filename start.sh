#!/usr/bin/env bash
# Käynnistää selainversion (Linux / macOS). Luo tarvittaessa .venv-ympäristön.
# Lisäparametrit välittyvät eteenpäin, esim. ./start.sh --host 0.0.0.0 --port 8765
set -e
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
. .venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
exec python -m ytlinks.web "$@"
