#!/bin/bash
set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "========================================================"
echo "      Lucerne Traffic Flow Simulator Launcher          "
echo "========================================================"

if [ ! -d ".venv" ]; then
    echo "Creating Python virtual environment (.venv)..."
    python3 -m venv .venv
    source .venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt
else
    source .venv/bin/activate
fi

echo "Initializing / verifying Lucerne map data cache..."
echo "(first run has no cache and fetches ~4200 nodes from OpenStreetMap - allow 3-6 minutes)"
python3 -m src.data_loader

echo "Starting Lucerne Traffic Simulator Web App on http://localhost:8000 ..."
exec uvicorn src.api:app --host 127.0.0.1 --port 8000
