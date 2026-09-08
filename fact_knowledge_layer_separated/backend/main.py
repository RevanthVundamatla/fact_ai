from pathlib import Path
import json
import os
import shutil

from fastapi import (
    FastAPI,
    UploadFile,
    File,
    HTTPException,
)

from fastapi.middleware.cors import CORSMiddleware

from .config import UPLOAD_DIR
from .db import init_db, get_db
from .services import (
    ingest_document,
    analyze_all,
    analyze_fact_ids,
)


# ============================================================
# APPLICATION
# ============================================================

app = FastAPI(
    title="Fact Knowledge Layer",
    version="1.0.0",
    description=(
        "PDF-grounded fact extraction and "
        "cross-document reasoning prototype."
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
            detail=(
                "At least one PDF file "
                "is required."
            ),
        )

    results = []

    # Keep track of new facts so that the caller
    # can optionally analyze them later.
    new_fact_ids = []

    for upload in files:

        # ----------------------------------------------------
        # Validate file
        # ----------------------------------------------------

        if (
            not upload.filename
            or not upload.filename
            .lower()
            .endswith(".pdf")
        ):

            raise HTTPException(
                status_code=400,
                detail=(
                    "Only PDF files are accepted."
                ),
            )

        # ----------------------------------------------------
        # Safe filename
        # ----------------------------------------------------

        safe_name = Path(
            upload.filename
        ).name

        if not safe_name:

            raise HTTPException(
                status_code=400,
                detail=(
                    "Invalid PDF filename."
                ),
            )

        target = (
            UPLOAD_DIR
            / safe_name
        )

        # ----------------------------------------------------
        # Save PDF
        # ----------------------------------------------------

        try:

            with target.open("wb") as out:

                shutil.copyfileobj(
                    upload.file,
                    out,
                )

        finally:

            await upload.close()

        # ----------------------------------------------------
        # Extract facts
        # ----------------------------------------------------

        try:

            doc_id, count = ingest_document(
                target
            )

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
        # Read document information
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
                        "Document was processed "
                        "but could not be read back."
                    ),
                )

            # ------------------------------------------------
            # Get IDs of facts belonging to this document.
            # ------------------------------------------------

            fact_rows = db.execute(
                """
                SELECT id
                FROM facts
                WHERE document_id = ?
                ORDER BY id
                """,
                (doc_id,),
            ).fetchall()

            new_fact_ids.extend(
                int(fact["id"])
                for fact in fact_rows
            )

        results.append(
            {
                "id": row["id"],
                "filename": row["filename"],
                "page_count": row["page_count"],
                "facts": count,
            }
        )

    # ========================================================
    # IMPORTANT:
    #
    # DO NOT RUN analyze_all() HERE.
    #
    # Upload should return immediately after extraction.
    # Relationship analysis is available through
    # POST /api/analyze.
    # ========================================================

    return {
        "documents": results,
        "facts_created": len(
            new_fact_ids
        ),
        "relationships_created": 0,
        "analysis_required": bool(
            new_fact_ids
        ),
        "message": (
            "Documents uploaded and facts "
            "extracted successfully. "
            "Run analysis to build "
            "cross-document relationships."
        ),
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

        # ----------------------------------------------------
        # Find facts that currently participate in no
        # relationship.
        #
        # These are treated as pending facts.
        # ----------------------------------------------------

        pending_rows = db.execute(
            """
            SELECT f.id
            FROM facts f
            LEFT JOIN relationships r1
                ON r1.fact_a = f.id
            LEFT JOIN relationships r2
                ON r2.fact_b = f.id
            WHERE r1.id IS NULL
              AND r2.id IS NULL
            ORDER BY f.id
            """
        ).fetchall()

        pending_ids = [
            int(row["id"])
            for row in pending_rows
        ]

    # --------------------------------------------------------
    # If there are no pending facts, don't rebuild the
    # entire relationship graph unnecessarily.
    # --------------------------------------------------------

    if not pending_ids:

        return {
            "documents_processed": documents,
            "facts_created": facts,
            "relationships_created": 0,
            "message": (
                "No pending facts require "
                "relationship analysis."
            ),
        }

    # --------------------------------------------------------
    # Incremental analysis
    # --------------------------------------------------------

    relationships = analyze_fact_ids(
        pending_ids
    )

    return {
        "documents_processed": documents,
        "facts_created": facts,
        "relationships_created": relationships,
        "pending_facts_analyzed": len(
            pending_ids
        ),
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

    return [
        dict(row)
        for row in rows
    ]


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
                    ON documents.id =
                       facts.document_id

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

@app.get(
    "/api/documents/{document_id}/facts"
)
def document_facts(
    document_id: int
):

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

    # --------------------------------------------------------
    # Remove uploaded PDFs.
    # --------------------------------------------------------

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
            "All documents, facts and "
            "relationships were deleted."
        ),
    }
