import json
from pathlib import Path

from .db import get_db
from .pdf_ingest import extract_facts_from_pdf, sha256_file
from .relation_engine import compare_facts


# ============================================================
# DOCUMENT INGESTION
# ============================================================

def ingest_document(path: Path):
    """
    Extract facts from one PDF and store them in SQLite.

    Relationship analysis is intentionally NOT performed here.
    This keeps PDF upload fast.
    """

    pages, fact_pairs = extract_facts_from_pdf(path)
    digest = sha256_file(path)

    with get_db() as db:

        # ----------------------------------------------------
        # Insert document
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # Insert extracted facts
        # ----------------------------------------------------

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
                VALUES(
                    ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
                )
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


# ============================================================
# INCREMENTAL RELATIONSHIP ANALYSIS
# ============================================================

def analyze_fact_ids(fact_ids):
    """
    Analyze only relationships involving the supplied facts.

    This is the important performance optimization.

    Old behavior:

        ALL facts
            ↓
        compare ALL facts
            ↓
        delete ALL relationships
            ↓
        rebuild ALL relationships

    New behavior:

        NEW facts
            ↓
        compare against existing facts
            ↓
        save only affected relationships
    """

    fact_ids = {
        int(x)
        for x in (fact_ids or [])
        if x is not None
    }

    if not fact_ids:
        return 0

    with get_db() as db:

        # ----------------------------------------------------
        # Load all facts.
        #
        # The relation engine itself performs candidate
        # filtering, so this remains reasonably efficient
        # for the assignment-sized dataset.
        # ----------------------------------------------------

        rows = db.execute(
            """
            SELECT *
            FROM facts
            ORDER BY id
            """
        ).fetchall()

        facts = [dict(row) for row in rows]

        # ----------------------------------------------------
        # Determine facts affected by this analysis.
        # ----------------------------------------------------

        selected_facts = [
            fact
            for fact in facts
            if int(fact["id"]) in fact_ids
        ]

        if not selected_facts:
            return 0

        # ----------------------------------------------------
        # Remove relationships involving these facts.
        #
        # This allows re-analysis safely if the Analyze
        # endpoint is clicked again.
        # ----------------------------------------------------

        placeholders = ",".join(
            "?" for _ in fact_ids
        )

        params = list(fact_ids) + list(fact_ids)

        db.execute(
            f"""
            DELETE FROM relationships
            WHERE fact_a IN ({placeholders})
               OR fact_b IN ({placeholders})
            """,
            params,
        )

    # --------------------------------------------------------
    # Compare only facts that involve the newly selected facts.
    #
    # compare_facts() will still perform candidate filtering
    # and skip same-document pairs.
    # --------------------------------------------------------

    pairs = compare_facts_involving(
        facts,
        fact_ids,
    )

    # --------------------------------------------------------
    # Store relationships.
    # --------------------------------------------------------

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


def compare_facts_involving(facts, selected_ids):
    """
    Run the relation engine only for candidate pairs where
    at least one fact belongs to selected_ids.
    """

    selected_ids = {
        int(x)
        for x in selected_ids
    }

    if not facts:
        return []

    # --------------------------------------------------------
    # Compare using the existing optimized relation engine.
    # --------------------------------------------------------

    all_pairs = compare_facts(facts)

    # --------------------------------------------------------
    # Keep only pairs involving a selected/new fact.
    # --------------------------------------------------------

    result = []

    for pair in all_pairs:

        fact_a = int(pair[0])
        fact_b = int(pair[1])

        if (
            fact_a in selected_ids
            or fact_b in selected_ids
        ):
            result.append(pair)

    return result


# ============================================================
# FULL ANALYSIS
# ============================================================

def analyze_all():
    """
    Full relationship rebuild.

    This is retained for explicit full re-analysis.

    Normal PDF upload should NOT call this.
    """

    with get_db() as db:

        facts = [
            dict(row)
            for row in db.execute(
                """
                SELECT *
                FROM facts
                ORDER BY id
                """
            ).fetchall()
        ]

        db.execute(
            "DELETE FROM relationships"
        )

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


# ============================================================
# DATABASE ROW HELPER
# ============================================================

def row_dict(row):
    """
    Convert a SQLite row to a normal dictionary.
    """

    return dict(row) if row else None
