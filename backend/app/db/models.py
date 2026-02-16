"""
SQLite database models and helpers (async via aiosqlite).
Tables: documents, workflows, runs, usage
"""

import aiosqlite
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "app.db")


async def get_db() -> aiosqlite.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    return db
