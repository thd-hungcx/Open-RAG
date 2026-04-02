"""Save response tool for OpenRAG MCP server."""

import logging
from datetime import datetime
from pathlib import Path

from mcp.types import TextContent, Tool

from openrag_mcp.tools.registry import register_tool

logger = logging.getLogger("openrag-mcp.save_response")

SAVE_RESPONSE_TOOL = Tool(
    name="save_response_to_file",
    description=(
        "Save a chat response to a .txt file in the openrag-documents folder on the server. "
        "Call this after getting a response to persist it locally."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "response": {
                "type": "string",
                "description": "The response text to save",
            },
            "filename": {
                "type": "string",
                "description": "Optional filename (without extension). Defaults to timestamp-based name.",
            },
        },
        "required": ["response"],
    },
)

# Resolve path relative to this file: sdks/mcp/src/openrag_mcp/tools/ -> project root
_PROJECT_ROOT = Path(__file__).resolve().parents[5]
_OUTPUT_DIR = _PROJECT_ROOT / "openrag-documents"


async def handle_save_response(arguments: dict) -> list[TextContent]:
    """Handle save_response_to_file tool calls."""
    response_text = arguments.get("response", "")
    filename = arguments.get("filename", "").strip()

    if not response_text:
        return [TextContent(type="text", text="Error: response is required")]

    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if not filename:
        filename = f"response_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # Sanitize filename
    filename = "".join(c if c.isalnum() or c in "-_" else "_" for c in filename)
    file_path = _OUTPUT_DIR / f"{filename}.txt"

    # Avoid overwriting: append counter if file exists
    counter = 1
    while file_path.exists():
        file_path = _OUTPUT_DIR / f"{filename}_{counter}.txt"
        counter += 1

    file_path.write_text(response_text, encoding="utf-8")
    logger.info(f"Response saved to {file_path}")

    return [TextContent(type="text", text=f"Response saved to: {file_path}")]


register_tool(SAVE_RESPONSE_TOOL, handle_save_response)
