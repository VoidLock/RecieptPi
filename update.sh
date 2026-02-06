#!/usr/bin/env bash
set -euo pipefail

# Update script: pull latest, source env, run alignment test

echo "Pulling latest changes..."
git pull origin main

echo "Sourcing .env..."
if [ ! -f .env ]; then
    echo "Error: .env not found. Copy .env.template to .env and fill in your config."
    exit 1
fi
source .env

echo "Running alignment test..."
python3 app.py --test-align

echo "Done!"
