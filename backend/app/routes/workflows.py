"""
/api/workflows – CRUD for workflows.
"""

import uuid
import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.db.models import get_db

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


class WorkflowCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    prompt_template: str
    output_schema_json: str
    created_by: Optional[str] = "user"


@router.get("")
async def list_workflows():
    db = await get_db()
    try:
        cursor = await db.execute(
            """
            SELECT w.*, COALESCE(u.run_count, 0) as run_count
            FROM workflows w
            LEFT JOIN usage u ON w.id = u.workflow_id
            ORDER BY w.created_at DESC
            """
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        await db.close()


@router.get("/{workflow_id}")
async def get_workflow(workflow_id: str):
    db = await get_db()
    try:
        cursor = await db.execute(
            """
            SELECT w.*, COALESCE(u.run_count, 0) as run_count
            FROM workflows w
            LEFT JOIN usage u ON w.id = u.workflow_id
            WHERE w.id = ?
            """,
            (workflow_id,),
        )
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Workflow not found")
        return dict(row)
    finally:
        await db.close()


@router.post("")
async def create_workflow(body: WorkflowCreate):
    # Validate that output_schema_json is valid JSON
    try:
        json.loads(body.output_schema_json)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=400, detail="output_schema_json must be valid JSON"
        )

    wf_id = str(uuid.uuid4())
    db = await get_db()
    try:
        await db.execute(
            """INSERT INTO workflows (id, name, description, prompt_template, output_schema_json, created_by)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                wf_id,
                body.name,
                body.description,
                body.prompt_template,
                body.output_schema_json,
                body.created_by,
            ),
        )
        await db.execute(
            "INSERT INTO usage (workflow_id, run_count) VALUES (?, 0)", (wf_id,)
        )
        await db.commit()
    finally:
        await db.close()

    return {"id": wf_id, "name": body.name, "message": "Workflow published successfully"}


@router.delete("/{workflow_id}")
async def delete_workflow(workflow_id: str):
    db = await get_db()
    try:
        cursor = await db.execute("SELECT id FROM workflows WHERE id = ?", (workflow_id,))
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Workflow not found")
        await db.execute("DELETE FROM usage WHERE workflow_id = ?", (workflow_id,))
        await db.execute("DELETE FROM workflows WHERE id = ?", (workflow_id,))
        await db.commit()
    finally:
        await db.close()
    return {"message": "Workflow deleted"}
