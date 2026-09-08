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
            "INSERT INTO documents(filename, stored_path, sha256, page_count) VALUES(?,?,?,?)",
            (path.name, str(path), digest, len(pages))
        )
        doc_id = cur.lastrowid
        for page, f in fact_pairs:
            db.execute("""INSERT INTO facts
                (document_id,page,text,evidence,fact_type,subject,predicate,value,unit,
                 normalized_value,normalized_unit,dates,entities,confidence,warnings)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (doc_id, page, f.text, f.evidence, f.fact_type, f.subject, f.predicate,
                 f.value, f.unit, f.normalized_value, f.normalized_unit,
                 json.dumps(f.dates), json.dumps(f.entities), f.confidence,
                 json.dumps(f.warnings)))
    return doc_id, len(fact_pairs)

def analyze_all():
    with get_db() as db:
        facts = [dict(r) for r in db.execute("SELECT * FROM facts").fetchall()]
        db.execute("DELETE FROM relationships")
    pairs = compare_facts(facts)
    with get_db() as db:
        for a,b,rel,score,explanation,signals in pairs:
            db.execute("""INSERT INTO relationships
                (fact_a,fact_b,relation,score,explanation,signals)
                VALUES(?,?,?,?,?,?)""", (a,b,rel,score,explanation,signals))
    return len(pairs)

def row_dict(r):
    return dict(r) if r else None
