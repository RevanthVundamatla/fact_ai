from pathlib import Path
import json
import os
import shutil

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .config import UPLOAD_DIR
from .db import init_db, get_db
from .services import ingest_document, analyze_all


app = FastAPI(
    title="Fact Knowledge Layer",
    version="1.0.0",
    description=(
        "PDF-grounded fact extraction and cross-document "
        "reasoning prototype."
    ),
)


# ============================================================
# CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# HEALTH
# ============================================================

@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "gemini_configured": bool(
            os.getenv("GEMINI_API_KEY")
        ),
        "supabase_configured": bool(
            os.getenv("SUPABASE_URL")
        ),
    }


# ============================================================
# STARTUP
# ============================================================

@app.on_event("startup")
def startup():
    init_db()


# ============================================================
# UPLOAD DOCUMENTS
# ============================================================

@app.post("/api/documents")
async def upload_documents(
    files: list[UploadFile] = File(...)
):
    if not files:
        raise HTTPException(
            status_code=400,
            detail="At least one PDF file is required."
        )

    results = []

    for upload in files:

        # ----------------------------------------------------
        # Validate extension
        # ----------------------------------------------------

        if (
            not upload.filename
            or not upload.filename.lower().endswith(".pdf")
        ):
            raise HTTPException(
                status_code=400,
                detail="Only PDF files are accepted."
            )

        # ----------------------------------------------------
        # Prevent path traversal
        # ----------------------------------------------------

        safe_name = Path(upload.filename).name

        if not safe_name:
            raise HTTPException(
                status_code=400,
                detail="Invalid PDF filename."
            )

        target = UPLOAD_DIR / safe_name

        # ----------------------------------------------------
        # Save uploaded PDF
        # ----------------------------------------------------

        try:
            with target.open("wb") as out:
                shutil.copyfileobj(upload.file, out)
        finally:
            await upload.close()

        # ----------------------------------------------------
        # Extract and store facts
        # ----------------------------------------------------

        try:
            doc_id, count = ingest_document(target)
        except Exception as exc:
            # Remove partially uploaded file if ingestion fails.
            if target.exists():
                target.unlink()

            raise HTTPException(
                status_code=500,
                detail=f"Failed to process {safe_name}: {exc}"
            )

        # ----------------------------------------------------
        # Read actual page count from database
        # ----------------------------------------------------

        with get_db() as db:
            row = db.execute(
                """
                SELECT
                    id,
                    filename,
                    page_count
                FROM documents
                WHERE id = ?
                """,
                (doc_id,)
            ).fetchone()

        if row is None:
            raise HTTPException(
                status_code=500,
                detail="Document was processed but could not be read back."
            )

        results.append(
            {
                "id": row["id"],
                "filename": row["filename"],
                "page_count": row["page_count"],
                "facts": count,
            }
        )

    # --------------------------------------------------------
    # Build cross-document relationships
    # --------------------------------------------------------

    try:
        relationships = analyze_all()
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Document ingestion succeeded but relationship analysis failed: {exc}"
        )

    return {
        "documents": results,
        "relationships_created": relationships,
    }


# ============================================================
# ANALYZE
# ============================================================

@app.post("/api/analyze")
def analyze():

    with get_db() as db:

        documents = db.execute(
            """
            SELECT COUNT(*) AS n
            FROM documents
            """
        ).fetchone()["n"]

        facts = db.execute(
            """
            SELECT COUNT(*) AS n
            FROM facts
            """
        ).fetchone()["n"]

    relationships = analyze_all()

    return {
        "documents_processed": documents,
        "facts_created": facts,
        "relationships_created": relationships,
    }


# ============================================================
# DOCUMENTS
# ============================================================

@app.get("/api/documents")
def documents():

    with get_db() as db:

        rows = db.execute(
            """
            SELECT
                d.id,
                d.filename,
                d.stored_path,
                d.sha256,
                d.page_count,
                d.created_at,
                COUNT(f.id) AS fact_count
            FROM documents d
            LEFT JOIN facts f
                ON f.document_id = d.id
            GROUP BY
                d.id,
                d.filename,
                d.stored_path,
                d.sha256,
                d.page_count,
                d.created_at
            ORDER BY d.id DESC
            """
        ).fetchall()

    return [dict(row) for row in rows]


# ============================================================
# ALL FACTS
# ============================================================

@app.get("/api/facts")
def facts():

    with get_db() as db:

        rows = [
            dict(row)
            for row in db.execute(
                """
                SELECT
                    facts.*,
                    documents.filename
                FROM facts
                JOIN documents
                    ON documents.id = facts.document_id
                ORDER BY facts.id DESC
                """
            ).fetchall()
        ]

    for row in rows:

        row["dates"] = json.loads(
            row.get("dates") or "[]"
        )

        row["entities"] = json.loads(
            row.get("entities") or "[]"
        )

        row["warnings"] = json.loads(
            row.get("warnings") or "[]"
        )

    return rows


# ============================================================
# FACTS FOR ONE DOCUMENT
# ============================================================

@app.get("/api/documents/{document_id}/facts")
def document_facts(document_id: int):

    with get_db() as db:

        # First make sure document exists.
        document = db.execute(
            """
            SELECT id, filename, page_count
            FROM documents
            WHERE id = ?
            """,
            (document_id,)
        ).fetchone()

        if document is None:
            raise HTTPException(
                status_code=404,
                detail="Document not found."
            )

        rows = [
            dict(row)
            for row in db.execute(
                """
                SELECT *
                FROM facts
                WHERE document_id = ?
                ORDER BY page, id
                """,
                (document_id,)
            ).fetchall()
        ]

    for row in rows:

        row["dates"] = json.loads(
            row.get("dates") or "[]"
        )

        row["entities"] = json.loads(
            row.get("entities") or "[]"
        )

        row["warnings"] = json.loads(
            row.get("warnings") or "[]"
        )

    return rows


# ============================================================
# RELATIONSHIPS
# ============================================================

@app.get("/api/relationships")
def relationships():

    with get_db() as db:

        rows = [
            dict(row)
            for row in db.execute(
                """
                SELECT
                    r.*,

                    da.filename AS document_a,
                    db.filename AS document_b,

                    fa.page AS page_a,
                    fb.page AS page_b,

                    fa.evidence AS evidence_a,
                    fb.evidence AS evidence_b,

                    fa.text AS fact_text_a,
                    fb.text AS fact_text_b,

                    fa.subject AS subject_a,
                    fb.subject AS subject_b,

                    fa.predicate AS predicate_a,
                    fb.predicate AS predicate_b,

                    fa.value AS value_a,
                    fb.value AS value_b,

                    fa.unit AS unit_a,
                    fb.unit AS unit_b

                FROM relationships r

                JOIN facts fa
                    ON fa.id = r.fact_a

                JOIN facts fb
                    ON fb.id = r.fact_b

                JOIN documents da
                    ON da.id = fa.document_id

                JOIN documents db
                    ON db.id = fb.document_id

                ORDER BY
                    r.score DESC,
                    r.id DESC
                """
            ).fetchall()
        ]

    for row in rows:

        row["signals"] = json.loads(
            row.get("signals") or "{}"
        )

    return rows


# ============================================================
# RESET
# ============================================================

@app.delete("/api/reset")
def reset():

    with get_db() as db:

        db.execute(
            "DELETE FROM relationships"
        )

        db.execute(
            "DELETE FROM facts"
        )

        db.execute(
            "DELETE FROM documents"
        )

    # Remove uploaded PDFs.
    if UPLOAD_DIR.exists():

        for path in UPLOAD_DIR.iterdir():

            if path.is_file():

                try:
                    path.unlink()
                except OSError:
                    pass

    return {
        "ok": True,
        "message": "All documents, facts and relationships were deleted."
    }
