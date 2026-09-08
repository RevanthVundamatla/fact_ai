# Fact Knowledge Layer — Engineering Intern Hiring Assignment

A production-oriented reference implementation for building a **Fact Knowledge Layer over PDFs**. It extracts grounded numerical/semantic facts, preserves page evidence, normalizes values and time scope, and finds corroboration, contradiction, and contextual reconciliation across documents.

## Architecture

```text
                    ┌──────────────────────┐
                    │ React + Vite frontend │
                    │ upload / facts / QA   │
                    └──────────┬───────────┘
                               │ REST / JSON
                               ▼
                    ┌──────────────────────┐
                    │    FastAPI backend   │
                    │ ingestion + reasoning│
                    └───────┬───────┬──────┘
                            │       │
                ┌───────────▼──┐ ┌──▼───────────┐
                │ SQLite local │ │ Gemini API   │
                │ offline mode │ │ optional AI  │
                └──────────────┘ └──────────────┘
                            │
                     optional sync
                            ▼
                    ┌────────────────┐
                    │ Supabase       │
                    │ PostgreSQL +   │
                    │ Storage        │
                    └────────────────┘
```

### Why this design
- **FastAPI** keeps the API and PDF pipeline simple and testable.
- **React/Vite** gives a clean deployable frontend separate from the backend.
- **SQLite** is the zero-setup local fallback for reviewers.
- **Supabase** is optional for hosted PostgreSQL/storage; the SQL migration is included.
- **Gemini** is optional. The deterministic pipeline remains usable without a paid model/API key, while Gemini can improve semantic extraction/review.
- Every extracted fact retains `document_id + page + evidence`, so the UI can always show its source.

## Project structure

```text
fact-knowledge-layer/
├── frontend/                 # React + Vite UI
│   ├── src/main.jsx
│   ├── src/styles.css
│   ├── package.json
│   ├── vite.config.js
│   └── .env.example
├── backend/                  # FastAPI API + intelligence pipeline
│   ├── main.py
│   ├── db.py
│   ├── models.py
│   ├── schemas.py
│   ├── pdf_ingest.py
│   ├── fact_extractor.py
│   ├── normalizer.py
│   ├── relation_engine.py
│   ├── services.py
│   ├── services/gemini_service.py
│   ├── services/supabase_service.py
│   ├── requirements.txt
│   └── .env.example
├── datasets/                 # supplied starter PDFs
├── evaluation/               # benchmark cases
├── supabase/migrations/      # hosted DB schema
├── tests/
├── docker/
│   ├── Dockerfile.backend
│   └── Dockerfile.frontend
└── docker-compose.yml
```

## Local setup

### Backend

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.main:app --reload
```

API: `http://127.0.0.1:8000`  
Swagger: `http://127.0.0.1:8000/docs`  
Health: `http://127.0.0.1:8000/api/health`

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open the Vite URL, normally `http://127.0.0.1:5173`.

The Vite dev server proxies `/api` to the FastAPI server.

## Gemini (optional)

Copy `backend/.env.example` to `backend/.env` and set:

```env
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-2.5-flash
```

The key is server-side only. **Never put it in React/Vite environment variables.**

The included adapter is deliberately optional: if Gemini fails or is not configured, the deterministic extraction/reasoning path continues to work.

## Supabase (optional hosted database)

Create a Supabase project, run `supabase/migrations/001_initial.sql` in the SQL editor, and configure:

```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your_server_side_key
```

The service-role key must stay on the backend. Do not commit `.env` files.

The current local reference pipeline uses SQLite by default; the Supabase schema is included so the same data model can be hosted without changing the frontend contract.

## Docker

Create `backend/.env` from `backend/.env.example`, then:

```bash
docker compose up --build
```

Frontend: `http://localhost:5173`  
Backend: `http://localhost:8000`

## API

- `POST /api/documents` — upload one or many PDFs and analyze them
- `POST /api/analyze` — re-run relationship analysis
- `GET /api/documents` — documents
- `GET /api/facts` — grounded facts
- `GET /api/documents/{id}/facts` — facts for one document
- `GET /api/relationships` — cross-document relationships
- `GET /api/health` — deployment health/configuration status
- `DELETE /api/reset` — clear local data

## Reasoning approach

Each fact is represented with:
- raw claim text;
- source document and page;
- evidence snippet;
- fact type;
- normalized numeric value/unit when possible;
- dates/time scope;
- extracted entities;
- confidence and warnings.

Relationships combine semantic similarity, entity overlap, numeric compatibility, unit compatibility, temporal overlap, scope signals and polarity/negation. This avoids treating a keyword match as a contradiction.

### Required demonstration cases

1. **Corroboration:** Delhivery FY24 service revenue — ₹81,415 million vs ₹8,142 crore. The system can reconcile the unit conversion and rounding.
2. **Likely contradiction:** India FY25 real GDP — 6.4% in the Economic Survey vs 6.5% in the IMF Article IV excerpt. The system should flag the difference while explaining that data-vintage/publication differences make it a *likely*, not proven, contradiction.
3. **Contextual reconciliation:** Q1/Q2/H1 FY25 GDP growth vs full-year FY25 GDP growth. Different time scopes mean the figures should not be treated as contradictory.
4. **Failure handling:** “1,509 employees moved to new roles” and “423 employees were promoted” appear near each other. A robust extractor must keep the predicates separate and preserve a warning/evidence trail rather than inventing a combined claim.

Benchmark definitions are in `evaluation/benchmark_cases.json`.

## Tests

```bash
pytest -q
```

The test suite covers normalization, extraction and relationship reasoning.

## Tradeoffs / limitations

- The default extractor is intentionally lightweight and deterministic; it is not a full legal/financial document parser.
- Complex tables, scanned PDFs and charts may need OCR/table-specific extraction.
- The optional Gemini adapter currently serves as an enhancement path rather than a hard dependency.
- Local SQLite is ideal for the assignment demo; production multi-user deployments should use PostgreSQL/Supabase and object storage.
- Relationship classifications are evidence-based heuristics, not a guarantee of truth.

## Next steps

1. Add OCR fallback for image-only PDFs.
2. Add page-region coordinates for click-to-highlight evidence.
3. Add async job queue for very large PDFs.
4. Add SHA-256 incremental ingestion/deduplication.
5. Add embedding/vector search for larger corpora.
6. Add explicit human-review workflow for low-confidence contradictions.
7. Add automated benchmark scoring and regression reports.
8. Add Supabase Storage upload/download and background processing.

## AI / coding tools

The implementation is designed so AI assistance can be used without making the system opaque: the README documents the architecture, the core deterministic reasoning is testable, and optional Gemini usage is isolated behind `backend/services/gemini_service.py`.

## Submission checklist

- [x] Separate frontend/backend
- [x] PDF upload and inspection UI
- [x] Page-level evidence grounding
- [x] Cross-document corroboration / contradiction / reconciliation
- [x] Starter PDFs included
- [x] Four benchmark cases
- [x] Automated tests
- [x] Docker deployment
- [x] Optional Gemini integration
- [x] Optional Supabase schema/integration scaffold
- [ ] Add your own <=3 minute demo video link before submission
- [ ] Add your GitHub repository link before submission
