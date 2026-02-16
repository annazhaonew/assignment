"""
AIXplore Team Workflow Library – FastAPI backend
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

from app.db.init_db import init_database
from app.routes import documents, workflows, runs


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_database()
    yield
    # Shutdown (nothing to clean up)


app = FastAPI(
    title="AIXplore Team Workflow Library",
    description="R&D workflow automation – parse PDFs, run AI analysis, share workflows",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS – allow React dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routers
app.include_router(documents.router)
app.include_router(workflows.router)
app.include_router(runs.router)


@app.get("/")
async def root():
    return {"message": "AIXplore Workflow Library API", "docs": "/docs"}
