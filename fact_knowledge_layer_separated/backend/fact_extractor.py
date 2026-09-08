import re
from .models import CandidateFact
from .normalizer import extract_dates, extract_period_tokens, extract_numeric

STOP = {
    "the","a","an","and","or","but","was","were","is","are","has","have",
    "had","this","that","with","from","for","in","on","of","to","by","as",
    "at","its","their","it","company","reported","according"
}

DECLARATIVE = re.compile(
    r"\b(is|was|were|are|has|had|reported|reached|recorded|generated|"
    r"operates|employs|acquired|sold|increased|decreased|grew|declined|"
    r"appointed|resigned|located|produces|produced|serves)\b",
    re.I
)

ENTITY_RE = re.compile(r"\b[A-Z][A-Za-z0-9&.-]*(?:\s+[A-Z][A-Za-z0-9&.-]*){0,4}\b")

def entities(text):
    vals = []
    for x in ENTITY_RE.findall(text):
        x = x.strip(" ,.;:()")
        if len(x) > 1 and x.lower() not in STOP:
            vals.append(x)
    return list(dict.fromkeys(vals))[:10]

def subject_guess(sentence):
    words = sentence.split()
    if not words:
        return None
    # Keep a compact leading noun phrase; later comparison uses entity overlap too.
    return " ".join(words[: min(5, len(words))])

def extract_page_facts(text, page):
    facts = []
    for raw in re.split(r"(?<=[.!?])\s+|\n+", text):
        sentence = re.sub(r"\s+", " ", raw).strip()
        if len(sentence) < 25 or len(sentence) > 600:
            continue
        value, unit, nv, nu = extract_numeric(sentence)
        is_decl = bool(DECLARATIVE.search(sentence))
        dates = extract_dates(sentence)
        periods = extract_period_tokens(sentence)
        ents = entities(sentence)

        if value is not None:
            confidence = 0.88
            warnings = []
            if not dates and periods:
                warnings.append("time period type found but exact date/year is missing")
            if not ents:
                confidence -= 0.12
                warnings.append("no strong named entity detected")
            facts.append(CandidateFact(
                text=sentence, evidence=sentence, fact_type="numerical",
                subject=subject_guess(sentence), predicate="contains_measurement",
                value=value, unit=unit, normalized_value=nv, normalized_unit=nu,
                dates=dates + periods, entities=ents, confidence=max(confidence, .1),
                warnings=warnings
            ))
        elif is_decl:
            confidence = 0.62
            warnings = ["semantic fact without an extracted numeric value"]
            if len(ents) == 0:
                confidence -= .12
                warnings.append("entity resolution may be ambiguous")
            facts.append(CandidateFact(
                text=sentence, evidence=sentence, fact_type="semantic",
                subject=subject_guess(sentence), predicate="assertion",
                dates=dates + periods, entities=ents, confidence=max(confidence, .1),
                warnings=warnings
            ))
    return facts
