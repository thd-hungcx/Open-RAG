"""Contract tools for OpenRAG MCP server.

Pipeline (knowledge base):
  1. contract_read_from_knowledge  — search knowledge base by filename, return text + detected blank fields
  2. contract_generate_from_text   — fill fields into text, save as .docx, return download URL

Pipeline (local .docx template):
  1. contract_list_files       — list .docx files available in openrag-documents/
  2. contract_read_template    — read .docx, return text + detected blank fields
  3. contract_generate_docx   — fill fields into original .docx, return download URL
"""

import logging
import re
import shutil
from datetime import datetime
from pathlib import Path

from mcp.types import TextContent, Tool

from openrag_mcp.config import get_config
from openrag_mcp.tools.registry import register_tool

logger = logging.getLogger("openrag-mcp.contract")

_DOCKER_DIR = Path("/app/openrag-documents")
_LOCAL_DIR = Path(__file__).resolve().parents[5] / "openrag-documents"
_OUTPUT_DIR = _DOCKER_DIR if _DOCKER_DIR.exists() else _LOCAL_DIR

_BLANK_PATTERN = re.compile(
    r"\{\{(\w+)\}\}"           # {{field}}
    r"|_{3,}"                  # ___
    r"\.{3,}"                  # ...
    r"|\[[\s_]*\]"             # [   ] or [___]
)
_PLACEHOLDER_PATTERN = re.compile(r"\{\{(\w+)\}\}")


def _sanitize(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in name)


def _unique_path(path: Path) -> Path:
    counter = 1
    base, suffix = path.stem, path.suffix
    while path.exists():
        path = path.with_name(f"{base}_{counter}{suffix}")
        counter += 1
    return path


def _iter_paragraphs(doc):
    """Yield all paragraphs including those inside tables."""
    yield from doc.paragraphs
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                yield from cell.paragraphs


def _get_placeholders(doc) -> list[str]:
    seen, result = set(), []
    for para in _iter_paragraphs(doc):
        for m in _PLACEHOLDER_PATTERN.finditer(para.text):
            key = m.group(1)
            if key not in seen:
                seen.add(key)
                result.append(key)
    return result


def _fill_doc(doc, fields: dict[str, str]):
    """Replace {{key}} → value in all runs, preserving run formatting."""
    def _replace_para(para):
        full = "".join(r.text for r in para.runs)
        replaced = _PLACEHOLDER_PATTERN.sub(
            lambda m: fields.get(m.group(1), ""), full
        )
        if replaced != full:
            for i, run in enumerate(para.runs):
                run.text = replaced if i == 0 else ""

    for para in _iter_paragraphs(doc):
        _replace_para(para)


# ---------------------------------------------------------------------------
# Tool 1: contract_list_files
# ---------------------------------------------------------------------------

async def handle_list_files(_: dict) -> list[TextContent]:
    files = "\n".join(f.name for f in _OUTPUT_DIR.glob("*.docx"))
    return [TextContent(type="text", text=files or "No .docx files found.")]

register_tool(
    Tool(
        name="contract_list_files",
        description="List all .docx contract template files available in openrag-documents/.",
        inputSchema={"type": "object", "properties": {}},
    ),
    handle_list_files,
)


# ---------------------------------------------------------------------------
# Tool 2: contract_read_template
# ---------------------------------------------------------------------------

async def handle_read_template(arguments: dict) -> list[TextContent]:
    try:
        from docx import Document
    except ImportError:
        return [TextContent(type="text", text="Error: python-docx is not installed")]

    filename = arguments.get("filename", "").strip()
    if not filename.endswith(".docx"):
        return [TextContent(type="text", text="Error: only .docx files are supported.")]

    file_path = _OUTPUT_DIR / Path(filename).name
    if not file_path.exists():
        return [TextContent(type="text", text=f"File not found: {filename}")]

    doc = Document(str(file_path))
    full_text = "\n".join(p.text for p in _iter_paragraphs(doc) if p.text.strip())
    placeholders = _get_placeholders(doc)

    if placeholders:
        fields_info = "Các trường cần điền ({{placeholder}}):\n" + "\n".join(f"- {p}" for p in placeholders)
    else:
        fields_info = (
            "Không tìm thấy {{placeholder}} rõ ràng.\n"
            "Hãy đọc nội dung bên dưới và tự xác định các chỗ trống (___) cần hỏi người dùng."
        )

    return [TextContent(type="text", text=f"{fields_info}\n\n---\n{full_text}")]


register_tool(
    Tool(
        name="contract_read_template",
        description=(
            "Read a LOCAL .docx contract template from openrag-documents/ folder and return its text + {{field}} placeholders. "
            "Only use this for files physically stored in openrag-documents/. "
            "If the user uploaded a contract to the knowledge base (via OpenRAG UI), use contract_read_from_knowledge instead."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "Name of the .docx file in openrag-documents/ (e.g. 'hop_dong_thue_nha.docx')",
                }
            },
            "required": ["filename"],
        },
    ),
    handle_read_template,
)


# ---------------------------------------------------------------------------
# Tool 3: contract_generate_docx
# ---------------------------------------------------------------------------

async def handle_generate_docx(arguments: dict) -> list[TextContent]:
    try:
        from docx import Document
    except ImportError:
        return [TextContent(type="text", text="Error: python-docx is not installed")]

    template_filename = arguments.get("template_filename", "").strip()
    fields: dict = arguments.get("fields", {})
    output_filename = arguments.get("output_filename", "").strip()

    if not template_filename.endswith(".docx"):
        return [TextContent(type="text", text="Error: only .docx templates are supported.")]

    template_path = _OUTPUT_DIR / Path(template_filename).name
    if not template_path.exists():
        return [TextContent(type="text", text=f"Template not found: {template_filename}")]

    # Copy template → new file to preserve all original formatting
    if not output_filename:
        output_filename = f"contract_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    out_path = _unique_path(_OUTPUT_DIR / f"{_sanitize(output_filename)}.docx")
    shutil.copy2(str(template_path), str(out_path))

    # Fill fields in the copy
    doc = Document(str(out_path))
    _fill_doc(doc, fields)
    doc.save(str(out_path))

    # Check remaining unfilled placeholders
    remaining = _get_placeholders(Document(str(out_path)))

    config = get_config()
    download_url = f"{config.openrag_url.rstrip('/')}/files/download/{out_path.name}"

    status = "✅ Tất cả các trường đã được điền." if not remaining else (
        f"⚠️ Còn {len(remaining)} trường chưa điền: {', '.join(remaining)}"
    )

    return [TextContent(
        type="text",
        text=(
            f"{status}\n\n"
            f"📄 **[Tải xuống: {out_path.name}]({download_url})**\n"
            f"`{download_url}`"
        ),
    )]


register_tool(
    Tool(
        name="contract_generate_docx",
        description=(
            "Fill a .docx contract template with user-provided field values and generate "
            "a downloadable file. Preserves original formatting. Only .docx supported. "
            "Call this after collecting all field values from the user."
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
                    "description": (
                        "Field name → value mapping. Fields not provided will be left blank. "
                        "Example: {\"ten_ben_a\": \"Công ty ABC\", \"ngay_ky\": \"01/04/2026\"}"
                    ),
                    "additionalProperties": {"type": "string"},
                },
                "output_filename": {
                    "type": "string",
                    "description": "Output filename without extension. Defaults to timestamp.",
                },
            },
            "required": ["template_filename", "fields"],
        },
    ),
    handle_generate_docx,
)


# ---------------------------------------------------------------------------
# Tool 4: contract_read_from_knowledge
# ---------------------------------------------------------------------------

async def handle_read_from_knowledge(arguments: dict) -> list[TextContent]:
    """Search knowledge base for a contract file and detect blank fields."""
    filename = arguments.get("filename", "").strip()
    if not filename:
        return [TextContent(type="text", text="Error: filename is required.")]

    config = get_config()
    import httpx

    # Search OpenRAG knowledge base for chunks belonging to this file
    async with httpx.AsyncClient(base_url=config.openrag_url, headers=config.headers, timeout=30) as client:
        resp = await client.post(
            "/api/search",
            json={"query": filename, "limit": 50, "data_sources": [filename]},
        )
        if resp.status_code != 200:
            return [TextContent(type="text", text=f"Search failed: {resp.status_code} {resp.text[:200]}")]

        data = resp.json()
        hits = data.get("results") or data.get("hits") or []

    if not hits:
        return [TextContent(type="text", text=f"Không tìm thấy file '{filename}' trong knowledge base. Hãy upload file trước.")]

    # Reconstruct full text from chunks (sorted by chunk index if available)
    hits.sort(key=lambda h: h.get("chunk_index", h.get("index", 0)))
    full_text = "\n".join(
        h.get("text") or h.get("content") or h.get("chunk_text", "") for h in hits
    ).strip()

    if not full_text:
        return [TextContent(type="text", text="Không đọc được nội dung file từ knowledge base.")]

    # Detect blank fields: {{field}}, [Field], <Field>, ___ patterns
    named_pattern = re.compile(r"\{\{(\w+)\}\}|\[([^\]]+)\]|<([^>]+)>")
    seen, placeholders = set(), []
    for m in named_pattern.finditer(full_text):
        key = (m.group(1) or m.group(2) or m.group(3)).strip()
        if key and key.lower() not in seen:
            seen.add(key.lower())
            placeholders.append(key)

    if placeholders:
        fields_info = "Các trường cần điền:\n" + "\n".join(f"- {p}" for p in placeholders)
    else:
        fields_info = "Không tìm thấy trường placeholder rõ ràng. Hãy đọc nội dung và xác định chỗ trống (___) cần hỏi người dùng."

    return [TextContent(type="text", text=f"{fields_info}\n\n---\n{full_text}")]


register_tool(
    Tool(
        name="contract_read_from_knowledge",
        description=(
            "Search the OpenRAG knowledge base for a contract file by filename, "
            "retrieve its full text content, and detect blank fields ({{field}}, [Field], <Field>) "
            "that need to be filled. Use this when the user mentions a contract file they uploaded."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "The filename of the contract in the knowledge base (e.g. 'hop_dong_thue_nha.pdf')",
                }
            },
            "required": ["filename"],
        },
    ),
    handle_read_from_knowledge,
)


# ---------------------------------------------------------------------------
# Tool 5: contract_generate_from_text
# ---------------------------------------------------------------------------

async def handle_generate_from_text(arguments: dict) -> list[TextContent]:
    """Fill fields into contract text and save as .docx."""
    try:
        from docx import Document as DocxDocument
    except ImportError:
        return [TextContent(type="text", text="Error: python-docx is not installed")]

    contract_text: str = arguments.get("contract_text", "").strip()
    fields: dict = arguments.get("fields", {})
    output_filename: str = arguments.get("output_filename", "").strip()

    if not contract_text:
        return [TextContent(type="text", text="Error: contract_text is required.")]

    # Fill all placeholder patterns
    filled = contract_text
    for key, value in fields.items():
        for tmpl in [f"{{{{{key}}}}}", f"[{key}]", f"<{key}>"]:
            filled = re.sub(re.escape(tmpl), str(value), filled, flags=re.IGNORECASE)

    # Save as .docx
    if not output_filename:
        output_filename = f"contract_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    out_path = _unique_path(_OUTPUT_DIR / f"{_sanitize(output_filename)}.docx")

    doc = DocxDocument()
    for line in filled.splitlines():
        doc.add_paragraph(line)
    doc.save(str(out_path))

    config = get_config()
    download_url = f"{config.openrag_url.rstrip('/')}/files/download/{out_path.name}"

    return [TextContent(
        type="text",
        text=f"✅ Hợp đồng đã được điền đầy đủ.\n\n📄 **[Tải xuống: {out_path.name}]({download_url})**\n`{download_url}`",
    )]


register_tool(
    Tool(
        name="contract_generate_from_text",
        description=(
            "Fill blank fields in a contract text retrieved from the knowledge base "
            "and generate a downloadable .docx file. "
            "Call this after collecting all field values from the user."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "contract_text": {
                    "type": "string",
                    "description": "The full contract text (retrieved from knowledge base)",
                },
                "fields": {
                    "type": "object",
                    "description": "Field name → value mapping. Example: {\"ten_ben_a\": \"Công ty ABC\"}",
                    "additionalProperties": {"type": "string"},
                },
                "output_filename": {
                    "type": "string",
                    "description": "Output filename without extension. Defaults to timestamp.",
                },
            },
            "required": ["contract_text", "fields"],
        },
    ),
    handle_generate_from_text,
)
