# AIXplore – Team Workflow Library

> **Reusable AI-powered workflows for R&D teams – parse clinical PDFs, extract structured insights, and validate outputs against source text.**

![Python](https://img.shields.io/badge/Python-3.12+-blue) ![FastAPI](https://img.shields.io/badge/FastAPI-0.114-009688) ![React](https://img.shields.io/badge/React-19-61DAFB) ![Azure OpenAI](https://img.shields.io/badge/Azure%20OpenAI-GPT--4o-orange) ![Azure Document Intelligence](https://img.shields.io/badge/Azure%20DI-prebuilt--layout-purple)

---

## Table of Contents

- [What is this?](#what-is-this)
- [Key Features](#key-features)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Setup & Installation](#setup--installation)
- [Running the App](#running-the-app)
- [How It Works – End to End](#how-it-works--end-to-end)
- [The Two Workflows](#the-two-workflows)
- [Grounding Validation & Self-Correction](#grounding-validation--self-correction)
- [Design Decisions & Trade-offs](#design-decisions--trade-offs)

---

## What is this?

**AIXplore** is a prototype for a _Team AI Infrastructure_ platform that lets R&D scientists create, share, and reuse AI-powered workflows. Instead of every team member writing one-off prompts, workflows are centralized: defined once, shared team-wide, and tracked for usage.

The prototype demonstrates this with **clinical/scientific paper analysis**: upload a PDF, pick a workflow, and get structured, validated JSON output — with every claim checked against the source text.

---

## Key Features

- 📄 **PDF Parsing** — Azure Document Intelligence (`prebuilt-layout`) extracts text, sections, tables, and span metadata
- 🖼️ **Figure Extraction** — PyMuPDF extracts images from PDFs; GPT-4o vision describes each figure
- 🧩 **Section-Based Chunking** — Long papers split at DI-detected sections, processed in parallel, then synthesized
- 📋 **Structured JSON Output** — LLM output constrained to a predefined JSON schema
- ✅ **Grounding Validation** — 3-layer system (stats matching + fuzzy quotes + LLM-as-judge) checks every claim
- 🔄 **Self-Correction Loop** — Ungrounded claims sent back to GPT-4o for correction or removal
- 📝 **Enriched Markdown Export** — Downloadable `.md` with inline tables and figure descriptions
- 📚 **Workflow Library** — Browse, create, delete, and track usage of team workflows
- ⚡ **Parallel Processing** — 6 threads for vision, 4 for text chunks
- 💾 **Figure Caching** — Vision results cached per document; subsequent runs skip expensive GPT-4o calls

---

## Architecture

```
┌──────────────────────────────────────────────────────┐
│                    React Frontend                    │
│   (Vite + TypeScript + Tailwind CSS, port 5173)      │
│                                                      │
│   ┌─────────┐  ┌──────────┐  ┌─────────────────┐     │
│   │ Library │  │   Run    │  │  Publish New    │     │
│   │  Page   │  │ Workflow │  │    Workflow     │     │
│   └─────────┘  └──────────┘  └─────────────────┘     │
└──────────────────────┬───────────────────────────────┘
                       │ REST API (axios)
                       ▼
┌──────────────────────────────────────────────────────-┐
│                  FastAPI Backend                      │
│            (Python 3.12+, port 8000)                  │
│                                                       │
│  Routes:                                              │
│   POST /api/documents/parse    → PDF parsing          │
│   GET  /api/workflows          → list workflows       │
│   POST /api/runs               → execute workflow     │
│   GET  /api/runs/{id}/download → download JSON        │
│   GET  /api/runs/{id}/download-md → download .md      │
│                                                       │
│  Services:                                            │
│   ┌─────────────┐  ┌────────────┐  ┌──────────────┐   │
│   │  doc_intel  │  │   aoai     │  │  grounding   │   │
│   │  (DI + PyMu)│  │  (GPT-4o)  │  │  (3-layer)   │   │
│   └──────┬──────┘  └─────┬──────┘  └──────┬───────┘   │
│          │               │                │           │
│          └───────┬───────┘                │           │
│                  ▼                        │           │
│          ┌─────────────-─┐                │           │
│          │workflow_runner│◄───────────────┘           │
│          │ (orchestrator)│                            │
│          └──────────────-┘                            │
│                                                       │
│  Storage: SQLite (aiosqlite) + file system            │
└─────────────────────────────────────────────────────-─┘
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
   ┌───────────-─┐ ┌─────────┐ ┌─────────────┐
   │ Azure Doc   │ │  Azure  │ │   SQLite    │
   │ Intelligence│ │ OpenAI  │ │   + Files   │
   │ (parsing)   │ │ (GPT-4o)│ │   (local)   │
   └────────────-┘ └─────────┘ └─────────────┘
```

---

## Tech Stack

### Backend

| Technology                  | Purpose                                      |
| --------------------------- | -------------------------------------------- |
| Python 3.12+                | Runtime                                      |
| FastAPI                     | Async REST API framework                     |
| aiosqlite                   | Async SQLite for workflows, runs, usage      |
| Azure Document Intelligence | PDF → text, tables, sections, spans          |
| PyMuPDF (fitz)              | Native image extraction from PDFs            |
| Azure OpenAI (GPT-4o)       | Analysis, vision, grounding, self-correction |
| python-dotenv               | Environment variable management              |

### Frontend

| Technology     | Purpose                     |
| -------------- | --------------------------- |
| React 19       | UI framework                |
| TypeScript     | Type safety                 |
| Vite           | Fast dev server and bundler |
| Tailwind CSS 4 | Utility-first styling       |
| React Router 7 | Client-side routing         |
| Axios          | HTTP client                 |

---

## Project Structure

```
workflow_prototype/
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI app, CORS, router mounting
│   │   ├── db/
│   │   │   ├── models.py            # SQLite connection helper
│   │   │   └── init_db.py           # Schema + seed workflows
│   │   ├── routes/
│   │   │   ├── documents.py         # POST /parse, GET /figure
│   │   │   ├── workflows.py         # CRUD for workflows
│   │   │   └── runs.py              # POST /runs, download endpoints
│   │   ├── services/
│   │   │   ├── doc_intel.py          # Azure DI + PyMuPDF image extraction
│   │   │   ├── aoai.py               # GPT-4o calls: vision, chunking, synthesis
│   │   │   ├── grounding.py          # 3-layer validation + self-correction
│   │   │   ├── workflow_runner.py    # Orchestrator: vision → LLM → grounding
│   │   │   └── enriched_md.py        # Builds enriched markdown with tables/figures
│   │   └── utils/
│   │       └── json_safe.py          # JSON parsing helpers
│   ├── data/                         # Runtime data (gitignored)
│   │   ├── app.db                    # SQLite database
│   │   ├── runs/                     # Saved run outputs (JSON + .md)
│   │   ├── parsed/                   # Parsed document text
│   │   ├── figures/                  # Extracted figure metadata
│   │   └── figure_descriptions/      # Cached GPT-4o vision results
│   └── .env.example                  # Environment variable template
├── frontend/
│   ├── src/
│   │   ├── main.tsx                  # React entry point
│   │   ├── api/client.ts             # API functions (axios)
│   │   ├── pages/
│   │   │   ├── Library.tsx           # Team workflow library
│   │   │   ├── RunWorkflow.tsx       # Upload + run workflow page
│   │   │   └── PublishWorkflow.tsx   # Create new workflows
│   │   └── components/
│   │       ├── Layout.tsx            # App shell with navigation
│   │       ├── UploadPanel.tsx       # PDF upload + parse
│   │       └── WorkflowOutput.tsx    # Results: triage/deep views, grounding
│   ├── index.html
│   ├── package.json
│   └── vite.config.ts
├── sample_papers/                    # Example PDFs for demo
├── requirements.txt                  # Python dependencies
└── README.md                         # This file
```

---

## Setup & Installation

### Prerequisites

- **Python 3.12+** (conda or venv)
- **Node.js 18+** and npm
- **Azure subscription** with:
  - Azure Document Intelligence resource
  - Azure OpenAI resource with a **GPT-4o** deployment

### 1. Clone the repository

```bash
git clone https://github.com/<your-username>/workflow_prototype.git
cd workflow_prototype
```

### 2. Backend setup

```bash
# Create and activate a Python environment
conda create -n prototype python=3.13 -y
conda activate prototype

# Install dependencies
pip install -r requirements.txt
```

### 3. Configure environment variables

```bash
cp backend/.env.example backend/.env
```

Edit `backend/.env` with your Azure credentials:

```dotenv
# Azure Document Intelligence
AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT=https://your-resource.cognitiveservices.azure.com/
AZURE_DOCUMENT_INTELLIGENCE_KEY=your-key-here

# Azure OpenAI
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=your-key-here
AZURE_OPENAI_MODEL_DEPLOYMENT=gpt-4o-deployment
AZURE_OPENAI_API_VERSION=2025-01-01-preview
```

### 4. Frontend setup

```bash
cd frontend
npm install
```

---

## Running the App

Open **two terminals**:

**Terminal 1 – Backend** (from project root):

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

**Terminal 2 – Frontend** (from project root):

```bash
cd frontend
npm run dev
```

Open [http://localhost:5173](http://localhost:5173) in your browser.

> The backend auto-creates the SQLite database and seeds two default workflows on first startup.

---

## How It Works – End to End

Here's the full pipeline when a user uploads a PDF and runs a workflow:

### Step 1: PDF Parsing (`doc_intel.py`)

```
PDF upload → Azure Document Intelligence (prebuilt-layout)
              │
              ├─ Extracted text (full content)
              ├─ Sections (with headings and offsets)
              ├─ Tables (HTML rendering)
              └─ Span metadata (for enriched markdown positioning)

         + PyMuPDF (fitz)
              │
              └─ Native image extraction
                  ├─ Filter: min 50×50px, min 2KB, max aspect ratio 12
                  ├─ Deduplicate by xref ID
                  └─ Output: base64-encoded images with page numbers
```

- **Azure Document Intelligence** provides structural understanding: headings, sections, tables with cell-level data.
- **PyMuPDF** extracts the actual embedded images (figures, charts, diagrams) directly from the PDF binary — more reliable than trying to identify figure regions from DI layout.
- Images are filtered to remove logos, icons, and decorative elements.

### Step 2: Figure Analysis (`aoai.py` — parallel vision)

```
Extracted images → GPT-4o Vision (6 parallel threads)
                    │
                    ├─ "NOT_A_FIGURE" → filtered out (logos, headers)
                    └─ Clinical description with:
                        ├─ Chart type identification
                        ├─ Key data points and trends
                        ├─ Statistical values from axes/labels
                        └─ Clinical significance
```

- Each image is sent to GPT-4o with a specialized clinical vision prompt.
- GPT-4o identifies non-figure images (logos, decorative) and returns `NOT_A_FIGURE`.
- Descriptions are **cached per document** in `data/figure_descriptions/` — subsequent runs skip this expensive step.
- Figures are matched to paper references (Figure 1, Figure 2, etc.) using sequential pairing.

### Step 3: Structured Analysis (`aoai.py` — chunking + synthesis)

```
Paper text + figure descriptions → Section-based chunking
                                     │
                                     ├─ Chunk 1 (sections 1-3) → GPT-4o → partial JSON
                                     ├─ Chunk 2 (sections 4-6) → GPT-4o → partial JSON
                                     └─ Chunk N (remaining)    → GPT-4o → partial JSON
                                                                    │
                                                                    ▼
                                                            Synthesis prompt
                                                            (merge all chunks)
                                                                    │
                                                                    ▼
                                                          Final structured JSON
```

- Long papers are split at DI-detected section boundaries (not arbitrary character counts).
- Small sections are merged until they hit a ~6000 character threshold.
- Each chunk is processed independently (4 parallel threads).
- A synthesis pass merges all partial outputs into a single JSON matching the workflow schema.
- Short papers (< threshold) skip chunking and go directly to GPT-4o.

### Step 4: Grounding Validation (`grounding.py`)

```
Structured JSON + source text → 3-layer validation
                                  │
                                  ├─ Layer 1: Value-based stat matching
                                  │   └─ Extract numbers, percentages, p-values,
                                  │     CIs, HRs from both output and source,
                                  │     then verify each stat appears in source
                                  │
                                  ├─ Layer 2: Fuzzy quote verification
                                  │   └─ Check supporting_quotes against source
                                  │     using token-level similarity (threshold: 0.60)
                                  │
                                  └─ Layer 3: LLM-as-judge
                                      └─ GPT-4o reviews each claim and rates:
                                          ✓ SUPPORTED – clearly in source
                                          ⚠ PARTIAL  – partially supported
                                          ✗ NOT_FOUND – not grounded in source
```

### Step 5: Self-Correction (`grounding.py` + `workflow_runner.py`)

```
Ungrounded claims → GPT-4o self-correction
                      │
                      ├─ Corrected claims (rewritten with source evidence)
                      └─ Removed claims (if no evidence exists)
                              │
                              ▼
                      Fast re-validation (regex + fuzzy only, no LLM)
                              │
                              ▼
                      Final grounding score with correction metadata
```

- If the grounding step finds errors, ungrounded claims are collected and sent back to GPT-4o.
- GPT-4o either **corrects** them (rewrites with proper source evidence) or **removes** them.
- The corrected output is re-validated using fast regex/fuzzy checks (skipping the LLM-as-judge to avoid latency).
- The UI shows correction metadata: what was changed, what was removed.

### Step 6: Output & Display

The frontend renders the validated output with:

- **Grounding banner**: overall score, claim counts (supported/partial/ungrounded), correction summary
- **Per-claim indicators**: inline ✓/⚠/✗ icons with hover details
- **Extracted figures**: actual images from the PDF with GPT-4o descriptions
- **Download options**: structured JSON and enriched markdown

---

## The Two Workflows

### 1. Clinical Paper Triage (Quick)

**Purpose**: Fast screening — should this paper be read in depth?

**Output schema**:

- `tldr` — one-paragraph summary
- `key_findings` — bullet points
- `biomarkers` — genes, proteins, lab measures
- `trial_phase_signals` — Phase I/II/III/Preclinical/Unknown
- `patient_population` — who was studied
- `follow_up_hypotheses` — next experiments to run
- `supporting_quotes` — 3-6 source quotes
- `confidence` — low/medium/high

**Processing**: Single-pass, no figure analysis, no chunking for short papers.

### 2. Deep Paper Analysis (Comprehensive)

**Purpose**: Full extraction with visual elements, statistical evidence, and safety data.

**Output schema**:

- `paper_metadata` — title, authors, journal, DOI
- `study_design` — type, methodology, sample size, duration
- `tldr` — summary
- `key_findings` — each with `finding`, `statistical_evidence`, `clinical_significance`
- `biomarkers_and_endpoints` — name, type, result
- `figures_and_tables_summary` — reference, description, key data
- `safety_profile` — adverse events, SAEs, discontinuation rate
- `limitations`, `clinical_implications`, `follow_up_hypotheses`
- `supporting_quotes` — 4-8 source quotes
- `confidence` — low/medium/high

**Processing**: Full pipeline with figure vision, section-based chunking, parallel processing.

---

## Grounding Validation & Self-Correction

This is the most technically interesting part. LLMs hallucinate. In pharma R&D, a hallucinated statistic could lead to wrong decisions. The grounding system ensures **every claim maps back to the source text**.

### Why 3 layers?

| Layer                 | Catches                                           | Speed   |
| --------------------- | ------------------------------------------------- | ------- |
| **Value-based stats** | Wrong numbers, fabricated p-values                | ⚡ Fast |
| **Fuzzy quotes**      | Paraphrased or fabricated quotes                  | ⚡ Fast |
| **LLM-as-judge**      | Subtle misinterpretations, unsupported inferences | 🐢 Slow |

- **Stats matching** extracts numbers/percentages/p-values from the output and searches for them in the source text
- **Fuzzy matching** checks supporting quotes against the source using token-level similarity (≥ 60%)
- **LLM judge** has GPT-4o cross-reference each claim against the source and rate it SUPPORTED / PARTIAL / NOT_FOUND

Each layer catches different failure modes. Stats matching is cheap and catches the most dangerous errors (wrong numbers). Fuzzy matching verifies quotes. The LLM judge catches nuanced errors that regex can't.

### Self-correction in action

```
Before correction:                    After correction:
─────────────────                    ──────────────────
"HR = 0.72 (95% CI 0.58-0.89)"     "HR = 0.64 (95% CI 0.58-0.71)"
  ✗ NOT_FOUND – stat not in source    ✓ SUPPORTED – corrected to source value

"Survival improved by 40%"           [REMOVED – no evidence in source]
  ✗ NOT_FOUND – percentage fabricated
```

---

## Design Decisions & Trade-offs

- **SQLite over PostgreSQL** — Prototype scope: zero setup, single-file DB, sufficient for demo
- **File-system caching** — Figure descriptions cached as JSON per document; simple, inspectable, no invalidation complexity
- **PyMuPDF over DI figures** — DI's figure detection was unreliable for clinical charts; PyMuPDF extracts actual embedded images
- **Sequential figure matching** — When image count = figure ref count, Figure N = Nth image in page order (simpler & more accurate)
- **Section-based chunking** — Splitting at DI-detected sections preserves context better than arbitrary character splits
- **Skip LLM on re-validation** — After self-correction, re-validate with regex/fuzzy only; avoids a second expensive GPT-4o call
- **Temperature 0.2** — Low temperature for structured extraction reduces randomness, improves consistency
- **Single correction round** — Diminishing returns after 1 round; keeps latency manageable

---

## Demo Walkthrough

1. **Open the app** → Library page shows two pre-seeded workflows with descriptions and run counts
2. **Click "Run this workflow →"** → Navigate to Run Workflow page
3. **Upload a clinical PDF** → Document Intelligence parses it; you see page count and text preview
4. **Click "Run Workflow"** → Watch the pipeline execute:
   - Figure extraction + GPT-4o vision
   - Section-based LLM analysis
   - Grounding validation + self-correction
5. **View results** → Structured output with grounding banner, per-claim indicators, and extracted figures
6. **Download** → Get the structured JSON or enriched markdown

---

## License

This is a prototype built for assessment purposes.
