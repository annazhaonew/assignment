"""
POST /api/runs – execute a workflow on a document.
GET  /api/runs/{run_id}/download – download run output as JSON.
GET  /api/runs/{run_id}/download-md – download enriched markdown.
"""

import uuid
import json
import os
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
from app.db.models import get_db
from app.services.workflow_runner import run_workflow
from app.services.enriched_md import build_enriched_markdown, save_enriched_markdown

router = APIRouter(prefix="/api/runs", tags=["runs"])

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")


class RunCreate(BaseModel):
    workflow_id: str
    doc_id: str
    input_text: Optional[str] = None


@router.post("")
async def execute_run(body: RunCreate):
    db = await get_db()
    try:
        # Fetch workflow
        cursor = await db.execute(
            "SELECT * FROM workflows WHERE id = ?", (body.workflow_id,)
        )
        workflow = await cursor.fetchone()
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")
        workflow = dict(workflow)

        # Fetch document
        cursor = await db.execute(
            "SELECT * FROM documents WHERE id = ?", (body.doc_id,)
        )
        doc = await cursor.fetchone()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        doc = dict(doc)

        # Get text
        text = body.input_text if body.input_text else doc.get("extracted_text", "")
        if not text:
            raise HTTPException(
                status_code=400, detail="No text available for processing"
            )

        # Get metadata (sections, span data, tables HTML)
        sections = []
        metadata = {}
        if doc.get("metadata"):
            metadata = json.loads(doc["metadata"])
            sections = metadata.get("sections", [])

        # Load figure images if available
        figure_images = []
        figures_path = os.path.join(DATA_DIR, "figures", f"{body.doc_id}.json")
        if os.path.exists(figures_path):
            with open(figures_path, "r") as f:
                figure_images = json.load(f)

        # Run the workflow
        try:
            result = await run_workflow(
                prompt_template=workflow["prompt_template"],
                output_schema_json=workflow["output_schema_json"],
                input_text=text,
                sections=sections,
                figure_images=figure_images,
                doc_id=body.doc_id,
            )
        except Exception as e:
            raise HTTPException(
                status_code=502,
                detail=f"Azure OpenAI error: {str(e)}",
            )

        # ── Generate enriched .md ──
        run_id = str(uuid.uuid4())
        figure_descriptions = result.get("figure_descriptions", [])
        grounding = result.get("grounding")

        original_path = os.path.join(DATA_DIR, "parsed", f"{body.doc_id}_original.txt")
        enriched_md_path = ""
        if os.path.exists(original_path):
            with open(original_path, "r", encoding="utf-8") as f:
                original_content = f.read()
            enriched_content = build_enriched_markdown(
                original_content=original_content,
                table_spans=metadata.get("table_spans", []),
                tables_html=metadata.get("tables_html", []),
                figure_spans=metadata.get("figure_spans", []),
                figure_descriptions=figure_descriptions,
                filename=doc.get("filename", "document.pdf"),
            )
            enriched_md_path = save_enriched_markdown(enriched_content, run_id)
        else:
            print(f"⚠️ Original content file not found: {original_path}")

        # Save run output as downloadable JSON
        output_str = json.dumps(result["parsed"]) if result["parsed"] else result["raw"]
        runs_dir = os.path.join(DATA_DIR, "runs")
        os.makedirs(runs_dir, exist_ok=True)
        run_output_path = os.path.join(runs_dir, f"{run_id}.json")
        with open(run_output_path, "w") as f:
            json.dump({
                "run_id": run_id,
                "workflow_name": workflow["name"],
                "document": doc.get("filename", ""),
                "output": result["parsed"],
                "figure_descriptions": figure_descriptions,
                "grounding": grounding,
                "raw_model_output": result["raw"],
                "enriched_md_path": enriched_md_path,
            }, f, indent=2)

        await db.execute(
            "INSERT INTO runs (id, workflow_id, document_id, output_json) VALUES (?, ?, ?, ?)",
            (run_id, body.workflow_id, body.doc_id, output_str),
        )

        # Update usage
        await db.execute(
            """INSERT INTO usage (workflow_id, run_count, last_run_at)
               VALUES (?, 1, CURRENT_TIMESTAMP)
               ON CONFLICT(workflow_id) DO UPDATE SET
                 run_count = run_count + 1,
                 last_run_at = CURRENT_TIMESTAMP""",
            (body.workflow_id,),
        )
        await db.commit()

        # Get updated run count
        cursor = await db.execute(
            "SELECT run_count FROM usage WHERE workflow_id = ?", (body.workflow_id,)
        )
        usage_row = await cursor.fetchone()
        run_count = dict(usage_row)["run_count"] if usage_row else 1

    finally:
        await db.close()

    return {
        "run_id": run_id,
        "output": result["parsed"],
        "raw_model_output": result["raw"],
        "figure_descriptions": figure_descriptions,
        "grounding": grounding,
        "has_enriched_md": bool(enriched_md_path),
        "usage": {"workflow_run_count": run_count},
    }


@router.get("/{run_id}/download")
async def download_run_output(run_id: str):
    """Download the full run output as JSON."""
    run_path = os.path.join(DATA_DIR, "runs", f"{run_id}.json")
    if not os.path.exists(run_path):
        raise HTTPException(status_code=404, detail="Run output file not found")

    return FileResponse(
        run_path,
        media_type="application/json",
        filename=f"run_{run_id}.json",
    )


@router.get("/{run_id}/download-md")
async def download_enriched_md(run_id: str):
    """Download the enriched markdown document."""
    md_path = os.path.join(DATA_DIR, "runs", f"{run_id}_enriched.md")
    if not os.path.exists(md_path):
        raise HTTPException(status_code=404, detail="Enriched .md not found")

    # Try to get original filename from the run JSON
    run_json_path = os.path.join(DATA_DIR, "runs", f"{run_id}.json")
    download_name = f"enriched_{run_id}.md"
    if os.path.exists(run_json_path):
        try:
            with open(run_json_path, "r") as f:
                run_data = json.load(f)
            orig = run_data.get("document", "")
            if orig:
                download_name = orig.replace(".pdf", "_enriched.md").replace(".PDF", "_enriched.md")
        except Exception:
            pass

    return FileResponse(
        md_path,
        media_type="text/markdown",
        filename=download_name,
    )
