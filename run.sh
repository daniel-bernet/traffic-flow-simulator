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
python3 -c "from src.data_loader import LucerneDataLoader; loader = LucerneDataLoader(); loader.load_data(use_cache=True)"

echo "Starting Lucerne Traffic Simulator Web App on http://localhost:8000 ..."
exec uvicorn src.api:app --host 0.0.0.0 --port 8000
