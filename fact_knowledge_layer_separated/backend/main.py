from pathlib import Path
import shutil
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .config import UPLOAD_DIR
from .db import init_db, get_db
from .services import ingest_document, analyze_all

app = FastAPI(
    title="Fact Knowledge Layer",
    version="1.0.0",
    description="PDF-grounded fact extraction and cross-document reasoning prototype."
)


app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.get("/api/health")
def health():
    return {"status":"ok","gemini_configured": bool(__import__("os").getenv("GEMINI_API_KEY")),"supabase_configured": bool(__import__("os").getenv("SUPABASE_URL"))}

@app.on_event("startup")
def startup():
    init_db()

@app.post("/api/documents")
async def upload_documents(files: list[UploadFile] = File(...)):
    results = []
    for upload in files:
        if not upload.filename or not upload.filename.lower().endswith(".pdf"):
            raise HTTPException(400, "Only PDF files are accepted.")
        safe_name = Path(upload.filename).name
        target = UPLOAD_DIR / safe_name
        with target.open("wb") as out:
            shutil.copyfileobj(upload.file, out)
        doc_id, count = ingest_document(target)
        results.append({"id": doc_id, "filename": safe_name, "facts": count})
    relationships = analyze_all()
    return {"documents": results, "relationships_created": relationships}

@app.post("/api/analyze")
def analyze():
    with get_db() as db:
        documents = db.execute("SELECT COUNT(*) AS n FROM documents").fetchone()["n"]
        facts = db.execute("SELECT COUNT(*) AS n FROM facts").fetchone()["n"]
    relationships = analyze_all()
    return {"documents_processed": documents, "facts_created": facts, "relationships_created": relationships}

@app.get("/api/documents")
def documents():
    with get_db() as db:
        return [dict(r) for r in db.execute("SELECT * FROM documents ORDER BY id DESC").fetchall()]

@app.get("/api/facts")
def facts():
    with get_db() as db:
        rows = [dict(r) for r in db.execute("""
            SELECT facts.*, documents.filename
            FROM facts JOIN documents ON documents.id=facts.document_id
            ORDER BY facts.id DESC
        """).fetchall()]
    import json
    for r in rows:
        r["dates"] = json.loads(r["dates"] or "[]")
        r["entities"] = json.loads(r["entities"] or "[]")
        r["warnings"] = json.loads(r["warnings"] or "[]")
    return rows

@app.get("/api/documents/{document_id}/facts")
def document_facts(document_id: int):
    with get_db() as db:
        rows = [dict(r) for r in db.execute(
            "SELECT * FROM facts WHERE document_id=? ORDER BY page,id", (document_id,)
        ).fetchall()]
    import json
    for r in rows:
        r["dates"] = json.loads(r["dates"] or "[]")
        r["entities"] = json.loads(r["entities"] or "[]")
        r["warnings"] = json.loads(r["warnings"] or "[]")
    return rows

@app.get("/api/relationships")
def relationships():
    with get_db() as db:
        rows = [dict(r) for r in db.execute("""
            SELECT r.*, da.filename AS document_a, db.filename AS document_b,
                   fa.page AS page_a, fb.page AS page_b,
                   fa.evidence AS evidence_a, fb.evidence AS evidence_b
            FROM relationships r
            JOIN facts fa ON fa.id=r.fact_a
            JOIN facts fb ON fb.id=r.fact_b
            JOIN documents da ON da.id=fa.document_id
            JOIN documents db ON db.id=fb.document_id
            ORDER BY r.score DESC, r.id DESC
        """).fetchall()]
    import json
    for r in rows:
        r["signals"] = json.loads(r["signals"] or "{}")
    return rows

@app.delete("/api/reset")
def reset():
    with get_db() as db:
        db.execute("DELETE FROM relationships")
        db.execute("DELETE FROM facts")
        db.execute("DELETE FROM documents")
    for p in UPLOAD_DIR.glob("*"):
        if p.is_file():
            p.unlink()
    return {"ok": True}
