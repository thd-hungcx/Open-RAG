#!/bin/bash
# Install local openrag-mcp package (with save_response tool) if available
if [ -d "/app/openrag-mcp" ]; then
    pip install -e /app/openrag-mcp --quiet
fi

exec langflow run --host 0.0.0.0 --port 7860 --components-path /app/flows/components
