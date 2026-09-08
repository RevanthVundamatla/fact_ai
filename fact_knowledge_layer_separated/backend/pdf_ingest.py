from pathlib import Path
import hashlib
import pymupdf
from .fact_extractor import extract_page_facts

def sha256_file(path: Path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def extract_pdf(path: Path):
    doc = pymupdf.open(path)
    pages = []
    for idx, page in enumerate(doc, start=1):
        text = page.get_text("text") or ""
        pages.append((idx, text))
    return pages

def extract_facts_from_pdf(path: Path):
    all_facts = []
    pages = extract_pdf(path)
    for page, text in pages:
        all_facts.extend((page, f) for f in extract_page_facts(text, page))
    return pages, all_facts
