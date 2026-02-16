"""
Initialise SQLite schema and seed workflows.
Called once on app startup.
"""

import json
from .models import get_db

DEFAULT_SCHEMA = json.dumps(
    {
        "tldr": "string",
        "key_findings": ["string"],
        "biomarkers": ["string"],
        "trial_phase_signals": "Phase I|Phase II|Phase III|Preclinical|Unknown",
        "patient_population": ["string"],
        "follow_up_hypotheses": ["string"],
        "supporting_quotes": ["string"],
        "confidence": "low|medium|high",
    },
    indent=2,
)

DEFAULT_PROMPT = """You will be given extracted text from a scientific PDF.
Produce a structured analysis as JSON using the exact schema provided.

Rules:
- Return JSON only (no markdown).
- Keep key_findings concise and specific.
- biomarkers: include gene/protein markers, lab measures, and pathway names if relevant.
- trial_phase_signals: infer from text. If not explicit, use Unknown.
- supporting_quotes: include 3-6 short quotes from the input that justify the key findings/phase/biomarkers.
- confidence: low if ambiguous, medium if partial evidence, high if explicit.

SCHEMA:
{schema_json}

PDF_TEXT:
{text}"""

# ── Second workflow: Deep Paper Analysis with Visual Elements ──

DEEP_ANALYSIS_SCHEMA = json.dumps(
    {
        "paper_metadata": {
            "title": "string",
            "authors": ["string"],
            "journal": "string",
            "year": "string",
            "doi": "string",
        },
        "study_design": {
            "type": "string (e.g. RCT, meta-analysis, cohort, case-control, review)",
            "methodology": "string",
            "sample_size": "string",
            "duration": "string",
        },
        "tldr": "string",
        "key_findings": [
            {
                "finding": "string",
                "statistical_evidence": "string (e.g. HR=0.64, 95% CI 0.58-0.71, p<0.001)",
                "clinical_significance": "string",
            }
        ],
        "biomarkers_and_endpoints": [
            {
                "name": "string",
                "type": "primary endpoint|secondary endpoint|biomarker|safety measure",
                "result": "string",
            }
        ],
        "figures_and_tables_summary": [
            {
                "reference": "string (e.g. Figure 1, Table 2)",
                "description": "string",
                "key_data": "string",
            }
        ],
        "safety_profile": {
            "adverse_events": ["string"],
            "serious_adverse_events": ["string"],
            "discontinuation_rate": "string",
        },
        "limitations": ["string"],
        "clinical_implications": ["string"],
        "follow_up_hypotheses": ["string"],
        "supporting_quotes": ["string"],
        "confidence": "low|medium|high",
    },
    indent=2,
)

DEEP_ANALYSIS_PROMPT = """You will be given extracted text from a scientific/clinical PDF, including any tables (in markdown format) and AI-generated descriptions of figures/diagrams.
Produce a comprehensive structured analysis as JSON using the exact schema provided.

Rules:
- Return JSON only (no markdown).
- paper_metadata: extract title, authors, journal, year, DOI from the text.
- study_design: identify the study type, methodology, sample size, and duration.
- key_findings: list each finding with its statistical evidence and clinical significance.
- biomarkers_and_endpoints: list all biomarkers, primary/secondary endpoints, and safety measures with their results.
- figures_and_tables_summary: summarize each figure and table referenced or described in the text. Include specific data points from the descriptions.
- safety_profile: extract adverse events, serious adverse events, and discontinuation rates.
- limitations: list study limitations mentioned by the authors.
- clinical_implications: what this means for clinical practice.
- supporting_quotes: include 4-8 short quotes from the input that justify the key findings.
- confidence: low if ambiguous, medium if partial evidence, high if explicit.

SCHEMA:
{schema_json}

PDF_TEXT:
{text}"""


async def init_database():
    db = await get_db()
    try:
        # ── Create tables ──
        await db.executescript(
            """
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                pages INTEGER,
                extracted_text TEXT,
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS workflows (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                prompt_template TEXT NOT NULL,
                output_schema_json TEXT NOT NULL,
                created_by TEXT DEFAULT 'system',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY,
                workflow_id TEXT NOT NULL,
                document_id TEXT NOT NULL,
                output_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (workflow_id) REFERENCES workflows(id),
                FOREIGN KEY (document_id) REFERENCES documents(id)
            );

            CREATE TABLE IF NOT EXISTS usage (
                workflow_id TEXT PRIMARY KEY,
                run_count INTEGER DEFAULT 0,
                last_run_at TIMESTAMP,
                FOREIGN KEY (workflow_id) REFERENCES workflows(id)
            );
            """
        )

        # Add metadata column if it doesn't exist (migration-safe)
        try:
            await db.execute("ALTER TABLE documents ADD COLUMN metadata TEXT")
            await db.commit()
        except Exception:
            pass  # Column already exists

        # ── Seed workflows if table is empty ──
        cursor = await db.execute("SELECT COUNT(*) FROM workflows")
        row = await cursor.fetchone()
        if row[0] == 0:
            import uuid

            # Workflow 1: Clinical Paper Triage (quick)
            wf1_id = str(uuid.uuid4())
            await db.execute(
                """INSERT INTO workflows (id, name, description, prompt_template, output_schema_json, created_by)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    wf1_id,
                    "Clinical Paper Triage → Summary, Biomarkers, Trial Phase, Next Experiments",
                    "Quick triage of a clinical/scientific PDF. Extracts key findings, biomarkers, trial phase signals, and follow-up hypotheses.",
                    DEFAULT_PROMPT,
                    DEFAULT_SCHEMA,
                    "system",
                ),
            )
            await db.execute(
                "INSERT INTO usage (workflow_id, run_count) VALUES (?, 0)", (wf1_id,)
            )

            # Workflow 2: Deep Paper Analysis with Visual Elements
            wf2_id = str(uuid.uuid4())
            await db.execute(
                """INSERT INTO workflows (id, name, description, prompt_template, output_schema_json, created_by)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    wf2_id,
                    "Deep Paper Analysis → Full Extraction with Figures, Tables & Safety Data",
                    "Comprehensive analysis of clinical papers including study design, statistical evidence, figure/table summaries (with AI vision), safety profiles, and clinical implications. Processes the full paper via section-based chunking.",
                    DEEP_ANALYSIS_PROMPT,
                    DEEP_ANALYSIS_SCHEMA,
                    "system",
                ),
            )
            await db.execute(
                "INSERT INTO usage (workflow_id, run_count) VALUES (?, 0)", (wf2_id,)
            )

            await db.commit()
            print(f"✅ Seeded workflow 1 (Quick Triage): {wf1_id}")
            print(f"✅ Seeded workflow 2 (Deep Analysis): {wf2_id}")

        await db.commit()
        print("✅ Database initialised")
    finally:
        await db.close()
