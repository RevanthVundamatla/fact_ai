import json
import re
from itertools import combinations
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

NEGATIONS = {"not", "no", "never", "none", "without", "didn't", "doesn't", "isn't", "wasn't"}
CHANGE_WORDS = {"increased","decreased","grew","declined","rose","fell","reduced","dropped"}

def tokens(s):
    return set(re.findall(r"[a-zA-Z][a-zA-Z0-9_-]+", (s or "").lower()))

def similarity(a, b):
    vec = TfidfVectorizer(ngram_range=(1,2), stop_words="english")
    X = vec.fit_transform([a, b])
    return float(cosine_similarity(X[0], X[1])[0,0])

def relationship(a, b):
    sem = similarity(a["text"], b["text"])
    ea = set(json.loads(a["entities"] or "[]"))
    eb = set(json.loads(b["entities"] or "[]"))
    entity_overlap = len(ea & eb) / max(1, len(ea | eb))

    same_unit = (
        a["normalized_unit"] and b["normalized_unit"]
        and a["normalized_unit"] == b["normalized_unit"]
    )
    numeric = None
    if a["normalized_value"] is not None and b["normalized_value"] is not None and same_unit:
        av, bv = a["normalized_value"], b["normalized_value"]
        numeric = 1.0 if max(abs(av), abs(bv), 1e-9) == 0 else min(abs(av-bv)/max(abs(av),abs(bv),1e-9), 1.0)

    dates_a = set(json.loads(a["dates"] or "[]"))
    dates_b = set(json.loads(b["dates"] or "[]"))
    date_overlap = len(dates_a & dates_b) > 0 if dates_a and dates_b else None

    period_a = set(x for x in dates_a if x in {"quarter","year","month","day"})
    period_b = set(x for x in dates_b if x in {"quarter","year","month","day"})
    different_period = bool(period_a and period_b and period_a != period_b)

    common = tokens(a["text"]) & tokens(b["text"])
    meaningful_overlap = len(common - NEGATIONS) >= 3

    score = 0.55 * sem + 0.30 * entity_overlap + 0.15 * (1.0 if meaningful_overlap else 0.0)

    signals = {
        "semantic_similarity": round(sem, 3),
        "entity_overlap": round(entity_overlap, 3),
        "normalized_unit_match": bool(same_unit),
        "relative_numeric_difference": None if numeric is None else round(numeric, 3),
        "date_overlap": date_overlap,
        "different_period_type": different_period
    }

    if score < 0.30:
        return "RELATED", score, "The statements have limited semantic/entity overlap; they are retained as related rather than forced into a stronger relationship.", signals

    if numeric is not None:
        if numeric <= 0.02 and (date_overlap is not False):
            return "CORROBORATES", score, "The statements refer to a compatible measurement after unit normalization, with overlapping or unspecified time context.", signals
        if different_period or date_overlap is False:
            return "RECONCILES", score, "The measurements differ, but the evidence indicates different time-period scopes, so the values need not conflict.", signals
        if numeric >= 0.10:
            return "CONTRADICTS", score, "Both statements describe a similar measurable fact in compatible units, but their normalized values materially disagree.", signals

    # Semantic contradiction heuristics.
    neg_a = bool(tokens(a["text"]) & NEGATIONS)
    neg_b = bool(tokens(b["text"]) & NEGATIONS)
    change_a = tokens(a["text"]) & CHANGE_WORDS
    change_b = tokens(b["text"]) & CHANGE_WORDS
    if sem >= 0.62 and neg_a != neg_b:
        return "CONTRADICTS", score, "The statements are semantically similar but differ in polarity/negation.", signals
    if sem >= 0.70 and change_a and change_b and change_a != change_b:
        return "CONTRADICTS", score, "The statements describe the same topic but assert opposing change directions.", signals

    return "RELATED", score, "The statements are sufficiently similar to inspect together, but the available evidence is not strong enough to label them corroborating or contradictory.", signals

def compare_facts(facts):
    pairs = []
    for a, b in combinations(facts, 2):
        if a["document_id"] == b["document_id"]:
            continue
        relation, score, explanation, signals = relationship(a, b)
        if relation in {"CORROBORATES","CONTRADICTS","RECONCILES"} or score >= 0.48:
            pairs.append((a["id"], b["id"], relation, score, explanation, json.dumps(signals)))
    return pairs
