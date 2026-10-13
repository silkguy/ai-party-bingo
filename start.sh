#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  echo 'Create the virtual environment first; see README.md.'
  exit 1
fi
exec .venv/bin/python launcher.py
