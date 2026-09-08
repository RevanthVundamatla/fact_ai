import json
from pathlib import Path

from .db import get_db
from .pdf_ingest import extract_facts_from_pdf, sha256_file
from .relation_engine import compare_facts


def ingest_document(path: Path):
    """
    Extract facts from a PDF and persist the document + facts.

    Relationship analysis is intentionally NOT performed here.
    This keeps PDF upload responsive and allows analysis to be
    triggered separately.
    """

    pages, fact_pairs = extract_facts_from_pdf(path)
    digest = sha256_file(path)

    with get_db() as db:
        # Prevent accidental duplicate ingestion of the same file.
        existing = db.execute(
            """
            SELECT id
            FROM documents
            WHERE sha256 = ?
            LIMIT 1
            """,
            (digest,),
        ).fetchone()

        if existing:
            return existing["id"], 0

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
                INSERT INTO facts(
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
                    json.dumps(
                        fact.dates,
                        ensure_ascii=False,
                    ),
                    json.dumps(
                        fact.entities,
                        ensure_ascii=False,
                    ),
                    fact.confidence,
                    json.dumps(
                        fact.warnings,
                        ensure_ascii=False,
                    ),
                ),
            )

    return doc_id, len(fact_pairs)


def analyze_all():
    """
    Rebuild all cross-document relationships.

    This operation is deliberately separate from document ingestion.

    Pipeline:
        1. Load all extracted facts.
        2. Remove stale relationships.
        3. Run the relationship engine.
        4. Persist corroboration / contradiction /
           reconciliation relationships.

    The relationship engine is responsible for:
        - numerical normalization
        - unit conversion
        - time-scope reasoning
        - topic compatibility
        - corroboration
        - contradiction
        - contextual reconciliation
        - semantic-reference safety
    """

    with get_db() as db:
        facts = [
            dict(row)
            for row in db.execute(
                """
                SELECT *
                FROM facts
                ORDER BY document_id, page, id
                """
            ).fetchall()
        ]

        # Relationships are derived data.
        # Rebuilding them prevents stale results after new ingestion.
        db.execute(
            """
            DELETE FROM relationships
            """
        )

    if len(facts) < 2:
        return 0

    # relation_engine.compare_facts() performs the actual
    # cross-document reasoning.
    pairs = compare_facts(facts)

    if not pairs:
        return 0

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
                INSERT INTO relationships(
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
    """
    Convert a SQLite row into a normal dictionary.
    """

    if row is None:
        return None

    return dict(row)
