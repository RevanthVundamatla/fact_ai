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
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    init_db()


# ============================================================
# UPLOAD DOCUMENTS
# ============================================================

@app.post("/api/documents")
async def upload_documents(
    files: list[UploadFile] = File(...)
):
    """
    Upload and ingest one or more PDFs.

    Important:
    Relationship analysis is NOT executed here.

    The endpoint only:
        1. validates the files
        2. saves them
        3. extracts facts
        4. stores documents + facts
        5. returns immediately

    This prevents slow uploads when many facts already exist.
    """

    if not files:
        raise HTTPException(
            status_code=400,
            detail="At least one PDF file is required.",
        )

    results = []

    for upload in files:

        # ----------------------------------------------------
        # Validate filename
        # ----------------------------------------------------

        if (
            not upload.filename
            or not upload.filename.lower().endswith(".pdf")
        ):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Only PDF files are accepted: "
                    f"{upload.filename or 'unnamed file'}"
                ),
            )

        safe_name = Path(upload.filename).name

        if not safe_name:
            raise HTTPException(
                status_code=400,
                detail="Invalid PDF filename.",
            )

        target = UPLOAD_DIR / safe_name

        # ----------------------------------------------------
        # Save uploaded PDF
        # ----------------------------------------------------

        try:
            with target.open("wb") as out:
                shutil.copyfileobj(
                    upload.file,
                    out,
                )

        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=(
                    f"Failed to save "
                    f"{safe_name}: {exc}"
                ),
            )

        finally:
            await upload.close()

        # ----------------------------------------------------
        # Extract and persist facts
        # ----------------------------------------------------

        try:
            doc_id, count = ingest_document(target)

        except Exception as exc:

            if target.exists():
                try:
                    target.unlink()
                except OSError:
                    pass

            raise HTTPException(
                status_code=500,
                detail=(
                    f"Failed to process "
                    f"{safe_name}: {exc}"
                ),
            )

        # ----------------------------------------------------
        # Read persisted document
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
                (doc_id,),
            ).fetchone()

        if row is None:
            raise HTTPException(
                status_code=500,
                detail=(
                    "Document was processed but "
                    "could not be read back."
                ),
            )

        # ----------------------------------------------------
        # Duplicate handling
        # ----------------------------------------------------
        #
        # ingest_document() returns count=0 when the exact
        # same SHA-256 document already exists.
        #
        # We still return the existing document normally.

        results.append(
            {
                "id": row["id"],
                "filename": row["filename"],
                "page_count": row["page_count"],
                "facts": count,
            }
        )

    return {
        "documents": results,
        "analysis_required": True,
        "message": (
            "Documents uploaded and facts extracted. "
            "Run /api/analyze to build cross-document "
            "relationships."
        ),
    }


# ============================================================
# ANALYZE
# ============================================================

@app.post("/api/analyze")
def analyze():
    """
    Run cross-document relationship reasoning.

    This is intentionally separate from upload so that:
        PDF upload -> fast
        relationship analysis -> explicit operation

    The relationship engine determines:
        - CORROBORATES
        - CONTRADICTS
        - RECONCILES
        - semantic/topic compatibility
    """

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

    if documents == 0 or facts < 2:
        return {
            "documents_processed": documents,
            "facts_created": facts,
            "relationships_created": 0,
            "message": (
                "Not enough data for cross-document analysis."
            ),
        }

    try:
        relationships = analyze_all()

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                f"Relationship analysis failed: {exc}"
            ),
        )

    return {
        "documents_processed": documents,
        "facts_created": facts,
        "relationships_created": relationships,
        "message": (
            "Cross-document relationship analysis completed."
        ),
    }


# ============================================================
# DOCUMENTS
# ============================================================

@app.get("/api/documents")
def documents():
    """
    Return all ingested documents.

    page_count is taken directly from the PDF ingestion layer.
    fact_count is calculated from the facts table.
    """

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

    return [
        dict(row)
        for row in rows
    ]


# ============================================================
# ALL FACTS
# ============================================================

@app.get("/api/facts")
def facts():
    """
    Return every extracted fact with source document metadata.

    JSON fields are decoded before returning them to the frontend.
    """

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

        row["dates"] = _safe_json_list(
            row.get("dates")
        )

        row["entities"] = _safe_json_list(
            row.get("entities")
        )

        row["warnings"] = _safe_json_list(
            row.get("warnings")
        )

    return rows


# ============================================================
# FACTS FOR ONE DOCUMENT
# ============================================================

@app.get("/api/documents/{document_id}/facts")
def document_facts(document_id: int):
    """
    Return all facts extracted from one document.
    """

    with get_db() as db:

        document = db.execute(
            """
            SELECT
                id,
                filename,
                page_count
            FROM documents
            WHERE id = ?
            """,
            (document_id,),
        ).fetchone()

        if document is None:
            raise HTTPException(
                status_code=404,
                detail="Document not found.",
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
                (document_id,),
            ).fetchall()
        ]

    for row in rows:

        row["dates"] = _safe_json_list(
            row.get("dates")
        )

        row["entities"] = _safe_json_list(
            row.get("entities")
        )

        row["warnings"] = _safe_json_list(
            row.get("warnings")
        )

    return rows


# ============================================================
# SINGLE FACT
# ============================================================

@app.get("/api/facts/{fact_id}")
def get_fact(fact_id: int):
    """
    Return one fact with its source document.

    Useful for frontend fact inspection and debugging.
    """

    with get_db() as db:

        row = db.execute(
            """
            SELECT
                f.*,
                d.filename,
                d.page_count
            FROM facts f
            JOIN documents d
                ON d.id = f.document_id
            WHERE f.id = ?
            """,
            (fact_id,),
        ).fetchone()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail="Fact not found.",
        )

    result = dict(row)

    result["dates"] = _safe_json_list(
        result.get("dates")
    )

    result["entities"] = _safe_json_list(
        result.get("entities")
    )

    result["warnings"] = _safe_json_list(
        result.get("warnings")
    )

    return result


# ============================================================
# RELATIONSHIPS
# ============================================================

@app.get("/api/relationships")
def relationships():
    """
    Return cross-document relationships together with the
    source evidence needed by the UI.

    Every relationship exposes:
        - relation type
        - confidence/score
        - explanation
        - reasoning signals
        - document names
        - source pages
        - source evidence
        - original fact text
        - subject/predicate/value/unit
    """

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
                    fb.unit AS unit_b,

                    fa.normalized_value AS normalized_value_a,
                    fb.normalized_value AS normalized_value_b,

                    fa.normalized_unit AS normalized_unit_a,
                    fb.normalized_unit AS normalized_unit_b,

                    fa.dates AS dates_a,
                    fb.dates AS dates_b,

                    fa.entities AS entities_a,
                    fb.entities AS entities_b,

                    fa.confidence AS confidence_a,
                    fb.confidence AS confidence_b,

                    fa.warnings AS warnings_a,
                    fb.warnings AS warnings_b

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

    # --------------------------------------------------------
    # Decode JSON fields
    # --------------------------------------------------------

    for row in rows:

        row["signals"] = _safe_json_object(
            row.get("signals")
        )

        row["dates_a"] = _safe_json_list(
            row.get("dates_a")
        )

        row["dates_b"] = _safe_json_list(
            row.get("dates_b")
        )

        row["entities_a"] = _safe_json_list(
            row.get("entities_a")
        )

        row["entities_b"] = _safe_json_list(
            row.get("entities_b")
        )

        row["warnings_a"] = _safe_json_list(
            row.get("warnings_a")
        )

        row["warnings_b"] = _safe_json_list(
            row.get("warnings_b")
        )

    return rows


# ============================================================
# RELATIONSHIP SUMMARY
# ============================================================

@app.get("/api/relationships/summary")
def relationship_summary():
    """
    Return relationship counts for dashboard/evaluation use.

    Keeping this calculation server-side avoids making the
    frontend infer relationship state.
    """

    with get_db() as db:

        total = db.execute(
            """
            SELECT COUNT(*) AS n
            FROM relationships
            """
        ).fetchone()["n"]

        rows = db.execute(
            """
            SELECT
                relation,
                COUNT(*) AS count
            FROM relationships
            GROUP BY relation
            ORDER BY count DESC
            """
        ).fetchall()

    by_relation = {
        row["relation"]: row["count"]
        for row in rows
    }

    return {
        "total": total,
        "by_relation": by_relation,
        "corroborates": by_relation.get(
            "CORROBORATES", 0
        ),
        "contradicts": by_relation.get(
            "CONTRADICTS", 0
        ),
        "reconciles": by_relation.get(
            "RECONCILES", 0
        ),
    }


# ============================================================
# RESET
# ============================================================

@app.delete("/api/reset")
def reset():
    """
    Delete all derived and source data from the local database
    and remove uploaded PDFs.
    """

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

    if UPLOAD_DIR.exists():

        for path in UPLOAD_DIR.iterdir():

            if path.is_file():

                try:
                    path.unlink()
                except OSError:
                    pass

    return {
        "ok": True,
        "message": (
            "All documents, facts and relationships "
            "were deleted."
        ),
    }


# ============================================================
# JSON HELPERS
# ============================================================

def _safe_json_list(value):
    """
    Safely decode a JSON array stored in SQLite.

    Bad/missing JSON should never break the entire API response.
    """

    if value is None:
        return []

    if isinstance(value, list):
        return value

    try:
        parsed = json.loads(value)

        if isinstance(parsed, list):
            return parsed

        return []

    except (
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ):
        return []


def _safe_json_object(value):
    """
    Safely decode a JSON object stored in SQLite.
    """

    if value is None:
        return {}

    if isinstance(value, dict):
        return value

    try:
        parsed = json.loads(value)

        if isinstance(parsed, dict):
            return parsed

        return {}

    except (
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ):
        return {}
