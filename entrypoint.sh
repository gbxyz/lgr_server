#!/bin/bash
set -euo pipefail

IFS=$'\n\t'

source /app/venv/bin/activate

/app/lgr_server.py "$@"
