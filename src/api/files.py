"""Serve generated files (e.g. filled .docx contracts) for user download."""

from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse

_DOCKER_DIR = Path("/app/openrag-documents")
_LOCAL_DIR = Path(__file__).resolve().parents[2] / "openrag-documents"
_FILES_DIR = _DOCKER_DIR if _DOCKER_DIR.exists() else _LOCAL_DIR

_MEDIA_TYPES = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pdf": "application/pdf",
}


async def download_file(filename: str):
    safe_name = Path(filename).name  # prevent path traversal
    file_path = _FILES_DIR / safe_name

    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {safe_name}")

    media_type = _MEDIA_TYPES.get(file_path.suffix, "application/octet-stream")
    return FileResponse(
        path=str(file_path),
        filename=safe_name,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{safe_name}"'},
    )
