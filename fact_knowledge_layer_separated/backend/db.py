import sqlite3
from contextlib import contextmanager
from .config import DATABASE_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    stored_path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    page_count INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    page INTEGER NOT NULL,
    text TEXT NOT NULL,
    evidence TEXT NOT NULL,
    fact_type TEXT NOT NULL,
    subject TEXT,
    predicate TEXT,
    value REAL,
    unit TEXT,
    normalized_value REAL,
    normalized_unit TEXT,
    dates TEXT,
    entities TEXT,
    confidence REAL NOT NULL,
    warnings TEXT,
    FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS relationships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fact_a INTEGER NOT NULL,
    fact_b INTEGER NOT NULL,
    relation TEXT NOT NULL,
    score REAL NOT NULL,
    explanation TEXT NOT NULL,
    signals TEXT,
    FOREIGN KEY(fact_a) REFERENCES facts(id) ON DELETE CASCADE,
    FOREIGN KEY(fact_b) REFERENCES facts(id) ON DELETE CASCADE
);
"""

@contextmanager
def get_db():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_db():
    with get_db() as db:
        db.executescript(SCHEMA)
