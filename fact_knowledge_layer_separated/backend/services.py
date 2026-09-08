import json
from pathlib import Path

from .db import get_db
from .pdf_ingest import extract_facts_from_pdf, sha256_file
from .relation_engine import compare_facts


def ingest_document(path: Path):
    pages, fact_pairs = extract_facts_from_pdf(path)
    digest = sha256_file(path)

    with get_db() as db:
        cur = db.execute(
            """
            INSERT INTO documents(
                filename,
                stored_path,
                sha256,
                page_count
            )
            VALUES(?,?,?,?)
            """,
            (
                path.name,
                str(path),
                digest,
                len(pages),
            ),
        )

        doc_id = cur.lastrowid

        for page, fact in fact_pairs:
            db.execute(
                """
                INSERT INTO facts
                (
                    document_id,
                    page,
                    text,
                    evidence,
                    fact_type,
                    subject,
                    predicate,
                    value,
                    unit,
                    normalized_value,
                    normalized_unit,
                    dates,
                    entities,
                    confidence,
                    warnings
                )
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    doc_id,
                    page,
                    fact.text,
                    fact.evidence,
                    fact.fact_type,
                    fact.subject,
                    fact.predicate,
                    fact.value,
                    fact.unit,
                    fact.normalized_value,
                    fact.normalized_unit,
                    json.dumps(fact.dates),
                    json.dumps(fact.entities),
                    fact.confidence,
                    json.dumps(fact.warnings),
                ),
            )

    return doc_id, len(fact_pairs)


def analyze_all():
    """
    Rebuild all cross-document relationships.

    This is intentionally kept as a separate operation.
    Uploading a PDF should not block on this step.
    """

    with get_db() as db:
        facts = [
            dict(row)
            for row in db.execute(
                "SELECT * FROM facts"
            ).fetchall()
        ]

        db.execute(
            "DELETE FROM relationships"
        )

    pairs = compare_facts(facts)

    with get_db() as db:
        for (
            fact_a,
            fact_b,
            relation,
            score,
            explanation,
            signals,
        ) in pairs:

            db.execute(
                """
                INSERT INTO relationships
                (
                    fact_a,
                    fact_b,
                    relation,
                    score,
                    explanation,
                    signals
                )
                VALUES(?,?,?,?,?,?)
                """,
                (
                    fact_a,
                    fact_b,
                    relation,
                    score,
                    explanation,
                    signals,
                ),
            )

    return len(pairs)


def row_dict(row):
    return dict(row) if row else None
