#!/bin/bash
# One-click start (macOS/Linux): starts Ollama if needed, warms up the model, starts the app, opens the browser.
cd "$(dirname "$0")"
if [ -x .venv/bin/python ]; then exec .venv/bin/python run.py; else exec python3 run.py; fi
