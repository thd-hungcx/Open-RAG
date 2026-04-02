"""Contract tools for OpenRAG MCP server.

Pipeline:
1. contract_parse_template  — detect {{field}} placeholders in a .docx
2. contract_fill_fields     — fill placeholders with provided values
3. contract_export_docx     — export final .docx to openrag-documents/
"""

import logging
import re
from datetime import datetime
from pathlib import Path

from mcp.types import TextContent, Tool

from openrag_mcp.tools.registry import register_tool

logger = logging.getLogger("openrag-mcp.contract")

_OUTPUT_DIR = Path("/app/openrag-documents")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sanitize(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in name)


def _unique_path(path: Path) -> Path:
    counter = 1
    base = path.stem
    while path.exists():
        path = path.with_name(f"{base}_{counter}{path.suffix}")
        counter += 1
    return path


def _find_placeholders(doc) -> list[str]:
    """Return unique {{field}} names found across all paragraphs and table cells."""
    pattern = re.compile(r"\{\{(\w+)\}\}")
    found: list[str] = []
    seen: set[str] = set()

    def _scan(text: str):
        for m in pattern.finditer(text):
            key = m.group(1)
            if key not in seen:
                seen.add(key)
                found.append(key)

    for para in doc.paragraphs:
        _scan(para.text)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for para in cell.paragraphs:
                    _scan(para.text)
    return found


def _fill_doc(doc, fields: dict[str, str]):
    """Replace {{key}} with value in all runs, preserving formatting."""
    pattern = re.compile(r"\{\{(\w+)\}\}")

    def _replace_para(para):
        # Rebuild full text, replace, then push back into first run
        full = "".join(r.text for r in para.runs)
        replaced = pattern.sub(lambda m: fields.get(m.group(1), m.group(0)), full)
        if replaced != full:
            for i, run in enumerate(para.runs):
                run.text = replaced if i == 0 else ""

    for para in doc.paragraphs:
        _replace_para(para)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for para in cell.paragraphs:
                    _replace_para(para)


# ---------------------------------------------------------------------------
# Tool 1: contract_parse_template
# ---------------------------------------------------------------------------

CONTRACT_PARSE_TOOL = Tool(
    name="contract_parse_template",
    description=(
        "Read a .docx contract template from openrag-documents/ and return all "
        "{{field}} placeholders that need to be filled in."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "filename": {
                "type": "string",
                "description": "Name of the .docx file in openrag-documents/ (e.g. 'hop_dong.docx')",
            }
        },
        "required": ["filename"],
    },
)


async def handle_parse_template(arguments: dict) -> list[TextContent]:
    try:
        from docx import Document
    except ImportError:
        return [TextContent(type="text", text="Error: python-docx is not installed")]

    filename = arguments.get("filename", "").strip()
    if not filename:
        return [TextContent(type="text", text="Error: filename is required")]

    file_path = _OUTPUT_DIR / filename
    if not file_path.exists():
        return [TextContent(type="text", text=f"Error: file not found: {file_path}")]

    doc = Document(str(file_path))
    placeholders = _find_placeholders(doc)

    if not placeholders:
        return [TextContent(type="text", text="No {{field}} placeholders found in the document.")]

    fields_list = "\n".join(f"- {{{{{f}}}}}" for f in placeholders)
    return [TextContent(
        type="text",
        text=f"Found {len(placeholders)} placeholder(s) in '{filename}':\n{fields_list}",
    )]


register_tool(CONTRACT_PARSE_TOOL, handle_parse_template)


# ---------------------------------------------------------------------------
# Tool 2: contract_fill_fields
# ---------------------------------------------------------------------------

CONTRACT_FILL_TOOL = Tool(
    name="contract_fill_fields",
    description=(
        "Fill {{field}} placeholders in a .docx template with provided values. "
        "Returns a preview of unfilled fields (if any) so the user can review before exporting."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "template_filename": {
                "type": "string",
                "description": "Source .docx template filename in openrag-documents/",
            },
            "fields": {
                "type": "object",
                "description": "Key-value pairs mapping field names to their values, e.g. {\"ten_ben_a\": \"Công ty ABC\"}",
                "additionalProperties": {"type": "string"},
            },
            "output_filename": {
                "type": "string",
                "description": "Optional output filename (without extension). Defaults to timestamp.",
            },
        },
        "required": ["template_filename", "fields"],
    },
)


async def handle_fill_fields(arguments: dict) -> list[TextContent]:
    try:
        from docx import Document
    except ImportError:
        return [TextContent(type="text", text="Error: python-docx is not installed")]

    template_filename = arguments.get("template_filename", "").strip()
    fields: dict = arguments.get("fields", {})
    output_filename = arguments.get("output_filename", "").strip()

    if not template_filename:
        return [TextContent(type="text", text="Error: template_filename is required")]

    template_path = _OUTPUT_DIR / template_filename
    if not template_path.exists():
        return [TextContent(type="text", text=f"Error: template not found: {template_path}")]

    doc = Document(str(template_path))

    # Check remaining unfilled fields
    all_placeholders = _find_placeholders(doc)
    unfilled = [f for f in all_placeholders if f not in fields]

    _fill_doc(doc, fields)

    # Save draft
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if not output_filename:
        output_filename = f"contract_draft_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    output_filename = _sanitize(output_filename)
    out_path = _unique_path(_OUTPUT_DIR / f"{output_filename}.docx")
    doc.save(str(out_path))

    msg = f"Draft saved to: {out_path.name}\n"
    if unfilled:
        msg += f"\n⚠️ Still unfilled: {', '.join('{{' + f + '}}' for f in unfilled)}"
    else:
        msg += "\n✅ All fields filled. Ready to export."

    return [TextContent(type="text", text=msg)]


register_tool(CONTRACT_FILL_TOOL, handle_fill_fields)


# ---------------------------------------------------------------------------
# Tool 3: contract_export_docx
# ---------------------------------------------------------------------------

CONTRACT_EXPORT_TOOL = Tool(
    name="contract_export_docx",
    description=(
        "Finalize and export the contract draft as a clean .docx file. "
        "Call this after the user has reviewed and approved the draft."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "draft_filename": {
                "type": "string",
                "description": "Draft .docx filename in openrag-documents/ to finalize",
            },
            "output_filename": {
                "type": "string",
                "description": "Final output filename (without extension)",
            },
        },
        "required": ["draft_filename", "output_filename"],
    },
)


async def handle_export_docx(arguments: dict) -> list[TextContent]:
    import shutil

    draft_filename = arguments.get("draft_filename", "").strip()
    output_filename = _sanitize(arguments.get("output_filename", "").strip())

    if not draft_filename or not output_filename:
        return [TextContent(type="text", text="Error: draft_filename and output_filename are required")]

    draft_path = _OUTPUT_DIR / draft_filename
    if not draft_path.exists():
        return [TextContent(type="text", text=f"Error: draft not found: {draft_path}")]

    out_path = _unique_path(_OUTPUT_DIR / f"{output_filename}.docx")
    shutil.copy2(str(draft_path), str(out_path))

    return [TextContent(type="text", text=f"✅ Contract exported: {out_path.name}")]


register_tool(CONTRACT_EXPORT_TOOL, handle_export_docx)
