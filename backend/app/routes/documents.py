"""
POST /api/documents/parse – upload PDF, extract text via Azure Document Intelligence.
GET  /api/documents/{doc_id}/figure/{index} – serve a figure image as PNG.
"""

import uuid
import os
import json
import base64
from io import BytesIO
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import Response
from app.db.models import get_db
from app.services.doc_intel import parse_pdf

router = APIRouter(prefix="/api/documents", tags=["documents"])

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")


@router.post("/parse")
async def parse_document(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    file_bytes = await file.read()
    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="Empty file.")

    try:
        result = await parse_pdf(file_bytes, filename=file.filename)
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"Azure Document Intelligence error: {str(e)}",
        )

    doc_id = str(uuid.uuid4())

    # Store in DB — include sections, span data, tables HTML for enriched .md later
    metadata = json.dumps({
        "sections": result.get("sections", []),
        "figure_count": len(result.get("figure_images", [])),
        "tables_count": len(result.get("tables_md", [])),
        "tables_html": result.get("tables_html", []),
        "table_spans": result.get("table_spans", []),
        "figure_spans": result.get("figure_spans", []),
    })

    db = await get_db()
    try:
        await db.execute(
            "INSERT INTO documents (id, filename, pages, extracted_text, metadata) VALUES (?, ?, ?, ?, ?)",
            (doc_id, file.filename, result["pages"], result["text"], metadata),
        )
        await db.commit()
    finally:
        await db.close()

    # Store figure images for the run step + UI serving
    figures_dir = os.path.join(DATA_DIR, "figures")
    os.makedirs(figures_dir, exist_ok=True)
    if result.get("figure_images"):
        figures_path = os.path.join(figures_dir, f"{doc_id}.json")
        with open(figures_path, "w") as f:
            json.dump(result["figure_images"], f)

    # Store original content for enriched .md generation after run
    original_dir = os.path.join(DATA_DIR, "parsed")
    os.makedirs(original_dir, exist_ok=True)
    original_path = os.path.join(original_dir, f"{doc_id}_original.txt")
    with open(original_path, "w", encoding="utf-8") as f:
        f.write(result.get("original_content", ""))

    return {
        "doc_id": doc_id,
        "filename": file.filename,
        "pages": result["pages"],
        "text": result["text"],
        "figures_detected": len(result.get("figure_images", [])),
        "tables_detected": len(result.get("tables_md", [])),
        "sections_detected": len(result.get("sections", [])),
    }


@router.get("/{doc_id}/figure/{index}")
async def get_figure_image(doc_id: str, index: int):
    """Serve a figure image as PNG by doc_id and 1-based figure index."""
    figures_path = os.path.join(DATA_DIR, "figures", f"{doc_id}.json")
    if not os.path.exists(figures_path):
        raise HTTPException(status_code=404, detail="No figures for this document")

    with open(figures_path, "r") as f:
        figures = json.load(f)

    for fig in figures:
        if fig["index"] == index:
            img_bytes = base64.b64decode(fig["image_base64"])
            return Response(
                content=img_bytes,
                media_type="image/png",
                headers={"Cache-Control": "public, max-age=86400"},
            )

    raise HTTPException(status_code=404, detail=f"Figure {index} not found")
