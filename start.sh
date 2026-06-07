#!/usr/bin/env bash

echo "========================================================"
echo "  Publikater - Mac/Linux Installer & Launcher"
echo "========================================================"

# Exit on error
set -e

# Check for uv
if ! command -v uv &> /dev/null; then
    echo "[INFO] 'uv' is not installed. Installing uv (fast Python package manager)..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    
    # Add uv to PATH for this session
    export PATH="$HOME/.cargo/bin:$PATH"
    
    if ! command -v uv &> /dev/null; then
        echo "[ERROR] Failed to install 'uv' or add it to PATH."
        echo "Please install uv manually from: https://docs.astral.sh/uv/getting-started/installation/"
        exit 1
    fi
else
    echo "[INFO] 'uv' is already installed."
fi

# Sync backend dependencies via uv
echo "[INFO] Syncing backend dependencies..."
cd backend
uv sync
cd ..

# Launch the app using uv's managed python
echo "[INFO] Launching Publikater..."
uv run --project backend python launcher.py
