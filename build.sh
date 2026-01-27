#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

echo "Creating virtual environment..."
python3 -m venv .venv

echo "Installing dependencies..."
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -e .

echo ""
echo "Done! To use friday:"
echo ""
echo "  source .venv/bin/activate"
echo "  friday auth"
echo ""
