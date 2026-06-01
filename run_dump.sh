#!/bin/bash
export HAGOKU_DUMP_LLM=1
exec .venv/bin/python -m uvicorn hagoku.api.server:app --host 0.0.0.0 --port 8000
