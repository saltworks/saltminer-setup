#!/bin/bash
set -e

# Activate virtual environment
source /opt/saltminer-dev/control-api/.venv/bin/activate

# Run the Flask app
exec python3 /opt/saltminer-dev/control-api/app.py