import json
import re
from collections import defaultdict
from itertools import combinations

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


NEGATIONS = {
    "not", "no", "never", "none", "without",
    "didn't", "doesn't", "isn't", "wasn't"
}

CHANGE_WORDS = {
    "increased", "decreased", "grew", "declined",
    "rose", "fell", "reduced", "dropped"
}

STOP_TOKENS = {
    "the", "and", "for", "from", "with", "that", "this",
    "were", "was", "are", "has", "have", "had", "into",
    "than", "then", "their", "there", "about", "during",
    "through", "under", "over", "year", "years", "period",
    "ended", "ending", "reported", "according", "estimated",
    "respectively", "per", "cent", "percent"
}


def safe_json_list(value):
    if not value:
        return []

    try:
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return parsed
    except (TypeError, json.JSONDecodeError):
        pass

    return []


def tokens(text):
    return set(
        re.findall(
            r"[a-zA-Z][a-zA-Z0-9_-]+",
            (text or "").lower()
        )
    )


def meaningful_tokens(text):
    return tokens(text) - STOP_TOKENS - NEGATIONS


def normalized_entities(fact):
    return {
        str(x).strip().lower()
        for x in safe_json_list(fact.get("entities"))
        if str(x).strip()
    }


def normalized_dates(fact):
    return {
        str(x).strip().lower()
        for x in safe_json_list(fact.get("dates"))
        if str(x).strip()
    }


def build_similarity_matrix(facts):
    if not facts:
        return None

    texts = [
        fact.get("text", "") or ""
        for fact in facts
    ]

    vectorizer = TfidfVectorizer(
        ngram_range=(1, 2),
        stop_words="english",
        max_features=20000,
        dtype=float,
    )

    try:
        return vectorizer.fit_transform(texts)
    except ValueError:
        return None


def similarity_from_matrix(matrix, i, j):
    return float(
        cosine_similarity(matrix[i], matrix[j])[0, 0]
    )


def numeric_value(fact):
    value = fact.get("normalized_value")

    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def unit(fact):
    return str(
        fact.get("normalized_unit")
        or fact.get("unit")
        or ""
    ).strip().lower()


def text_contains_any(text, words):
    text = (text or "").lower()
    return any(word in text for word in words)


def fiscal_year_tokens(fact):
    text = (fact.get("text") or "").lower()

    years = set(
        re.findall(
            r"(?:fy\s*)?(20\d{2})(?:[-/](?:20)?\d{2})?",
            text
        )
    )

    dates = normalized_dates(fact)

    for item in dates:
        found = re.findall(r"20\d{2}", item)
        years.update(found)

    return years


def period_scope(fact):
    """
    Classify broad time scope.

    This deliberately uses text + extracted dates because
    the extractor can miss some temporal structure.
    """
    text = (fact.get("text") or "").lower()

    scopes = set()

    if re.search(r"\bq[1-4]\b", text):
        scopes.add("quarter")

    if re.search(r"\b(first|second|third|fourth)\s+quarter\b", text):
        scopes.add("quarter")

    if re.search(r"\bhalf[- ]year\b|\bh1\b|\bh2\b", text):
        scopes.add("half-year")

    if re.search(r"\bfy\s*20\d{2}\b", text):
        scopes.add("fiscal-year")

    if re.search(r"\b20\d{2}/\d{2,4}\b", text):
        scopes.add("fiscal-year")

    if re.search(r"\b20\d{2}\b", text):
        scopes.add("year")

    return scopes


def same_subject_signal(a, b):
    """
    Strong subject overlap based on entities and text.

    We do not require exact entity equality because PDF
    extraction can produce slightly different entity strings.
    """
    entities_a = normalized_entities(a)
    entities_b = normalized_entities(b)

    if entities_a & entities_b:
        return True

    text_a = meaningful_tokens(a.get("text", ""))
    text_b = meaningful_tokens(b.get("text", ""))

    shared = text_a & text_b

    important = {
        "revenue", "services", "growth", "gdp", "employees",
        "workforce", "pin", "codes", "customers", "facilities",
        "parcels", "freight", "team", "size", "mobility",
        "promotion", "promoted"
    }

    return bool(shared & important)


def candidate_pairs(facts):
    """
    Candidate generation is intentionally broader than the
    previous implementation.

    Important:
    ₹ million vs ₹ crore may have different normalized units
    depending on the extractor, so unit equality cannot be a
    hard candidate requirement.
    """

    if not facts:
        return []

    buckets = defaultdict(set)

    for index, fact in enumerate(facts):
        entities = normalized_entities(fact)
        text_tokens = meaningful_tokens(fact.get("text", ""))

        # Entity buckets
        for entity in entities:
            buckets[("entity", entity)].add(index)

        # Important domain tokens
        for token in text_tokens:
            if len(token) >= 4:
                buckets[("token", token)].add(index)

        # Time-independent numerical/topic bucket
        for token in {
            "revenue", "gdp", "growth", "employees",
            "workforce", "customers", "facilities",
            "pin", "codes", "services"
        }:
            if token in text_tokens:
                buckets[("important", token)].add(index)

    pairs = set()

    for group in buckets.values():
        if len(group) < 2:
            continue

        # Avoid huge generic buckets.
        if len(group) > 150:
            continue

        for i, j in combinations(sorted(group), 2):
            a = facts[i]
            b = facts[j]

            if a.get("document_id") == b.get("document_id"):
                continue

            pairs.add((i, j))

    return list(pairs)


def numeric_difference(a, b):
    av = numeric_value(a)
    bv = numeric_value(b)

    if av is None or bv is None:
        return None

    ua = unit(a)
    ub = unit(b)

    # Same normalized unit.
    if ua and ub and ua == ub:
        denominator = max(abs(av), abs(bv), 1e-9)
        return min(abs(av - bv) / denominator, 1.0)

    return None


def convert_value(value, from_unit, to_unit):
    """
    Minimal generic conversion layer for common financial units.

    1 crore = 10 million.
    """
    if value is None:
        return None

    if from_unit == to_unit:
        return value

    aliases = {
        "million": "million",
        "mn": "million",
        "₹ million": "million",
        "inr million": "million",
        "crore": "crore",
        "cr": "crore",
        "₹ crore": "crore",
        "inr crore": "crore",
    }

    f = aliases.get(from_unit, from_unit)
    t = aliases.get(to_unit, to_unit)

    if f == t:
        return value

    if f == "million" and t == "crore":
        return value / 10.0

    if f == "crore" and t == "million":
        return value * 10.0

    return None


def cross_unit_difference(a, b):
    """
    Compare values even when the extractor retained different
    financial units.

    Example:
        81,415 million
        8,142 crore

    81,415 million = 8,141.5 crore.
    Difference from 8,142 crore is ~0.006%.
    """
    av = numeric_value(a)
    bv = numeric_value(b)

    if av is None or bv is None:
        return None, None

    ua = unit(a)
    ub = unit(b)

    converted_a = convert_value(av, ua, ub)

    if converted_a is None:
        converted_b = convert_value(bv, ub, ua)

        if converted_b is None:
            return None, None

        denominator = max(abs(av), abs(converted_b), 1e-9)
        difference = min(
            abs(av - converted_b) / denominator,
            1.0
        )

        return difference, {
            "conversion": f"{ub} -> {ua}",
            "converted_value_b": round(converted_b, 6),
        }

    denominator = max(
        abs(converted_a),
        abs(bv),
        1e-9
    )

    difference = min(
        abs(converted_a - bv) / denominator,
        1.0
    )

    return difference, {
        "conversion": f"{ua} -> {ub}",
        "converted_value_a": round(converted_a, 6),
    }


def date_overlap(a, b):
    dates_a = normalized_dates(a)
    dates_b = normalized_dates(b)

    if not dates_a or not dates_b:
        return None

    return bool(dates_a & dates_b)


def different_time_scope(a, b):
    scope_a = period_scope(a)
    scope_b = period_scope(b)

    # Explicitly different scopes.
    if scope_a and scope_b and scope_a != scope_b:
        return True

    text_a = (a.get("text") or "").lower()
    text_b = (b.get("text") or "").lower()

    # Quarter vs annual/fiscal-year.
    quarter_a = bool(re.search(r"\bq[1-4]\b", text_a))
    quarter_b = bool(re.search(r"\bq[1-4]\b", text_b))

    annual_a = bool(
        re.search(r"\bfy\s*20\d{2}\b|\b20\d{2}/\d{2,4}\b", text_a)
    )
    annual_b = bool(
        re.search(r"\bfy\s*20\d{2}\b|\b20\d{2}/\d{2,4}\b", text_b)
    )

    if (quarter_a and annual_b) or (quarter_b and annual_a):
        return True

    # Half-year vs annual.
    half_a = bool(re.search(r"\bh1\b|\bh2\b|half[- ]year", text_a))
    half_b = bool(re.search(r"\bh1\b|\bh2\b|half[- ]year", text_b))

    if (half_a and annual_b) or (half_b and annual_a):
        return True

    return False


def relationship(a, b, sem=None):
    if sem is None:
        matrix = build_similarity_matrix([a, b])

        if matrix is None:
            sem = 0.0
        else:
            sem = similarity_from_matrix(matrix, 0, 1)

    entities_a = normalized_entities(a)
    entities_b = normalized_entities(b)

    entity_overlap = len(
        entities_a & entities_b
    ) / max(
        1,
        len(entities_a | entities_b)
    )

    common_tokens = (
        meaningful_tokens(a.get("text", ""))
        &
        meaningful_tokens(b.get("text", ""))
    )

    meaningful_overlap = len(common_tokens)

    subject_signal = same_subject_signal(a, b)

    same_unit = (
        bool(unit(a))
        and bool(unit(b))
        and unit(a) == unit(b)
    )

    direct_difference = numeric_difference(a, b)
    converted_difference, conversion_info = cross_unit_difference(a, b)

    numeric_diff = (
        direct_difference
        if direct_difference is not None
        else converted_difference
    )

    dates_overlap = date_overlap(a, b)
    time_scope_diff = different_time_scope(a, b)

    # Entity + semantic + meaningful words.
    score = (
        0.45 * sem
        + 0.25 * entity_overlap
        + 0.15 * min(meaningful_overlap / 6.0, 1.0)
        + 0.15 * (1.0 if subject_signal else 0.0)
    )

    signals = {
        "semantic_similarity": round(sem, 3),
        "entity_overlap": round(entity_overlap, 3),
        "meaningful_token_overlap": meaningful_overlap,
        "subject_signal": subject_signal,
        "normalized_unit_match": same_unit,
        "relative_numeric_difference": (
            None
            if numeric_diff is None
            else round(numeric_diff, 5)
        ),
        "date_overlap": dates_overlap,
        "different_time_scope": time_scope_diff,
        "unit_conversion": conversion_info,
    }

    # ---------------------------------------------------------
    # Numerical relationships
    # ---------------------------------------------------------

    if numeric_diff is not None:

        # Same scope + near-identical value.
        if numeric_diff <= 0.02 and not time_scope_diff:
            conversion_text = ""

            if conversion_info:
                conversion_text = (
                    f" Unit conversion was applied "
                    f"({conversion_info['conversion']})."
                )

            return (
                "CORROBORATES",
                max(score, 0.75),
                (
                    "The statements describe the same measurable "
                    "fact and their values agree after normalization"
                    f"{conversion_text} "
                    "The small remaining difference is consistent "
                    "with rounding/display precision."
                ),
                signals,
            )

        # Different scopes should not be called contradiction.
        if time_scope_diff:
            return (
                "RECONCILES",
                max(score, 0.60),
                (
                    "The measurements differ because the statements "
                    "refer to different time scopes or reporting "
                    "periods. They are therefore contextual rather "
                    "than directly contradictory."
                ),
                signals,
            )

        # Small but non-trivial difference.
        if numeric_diff < 0.10:
            return (
                "RELATED",
                score,
                (
                    "The statements concern a similar measurable "
                    "fact, but the numerical difference is not large "
                    "enough to establish a contradiction and not "
                    "small enough to confidently call corroboration."
                ),
                signals,
            )

        # Material difference.
        if numeric_diff >= 0.10:
            return (
                "CONTRADICTS",
                max(score, 0.55),
                (
                    "The statements appear to describe the same "
                    "measurable fact in comparable units, but their "
                    "normalized values differ materially."
                ),
                signals,
            )

    # ---------------------------------------------------------
    # Semantic relationships
    # ---------------------------------------------------------

    tokens_a = tokens(a.get("text", ""))
    tokens_b = tokens(b.get("text", ""))

    neg_a = bool(tokens_a & NEGATIONS)
    neg_b = bool(tokens_b & NEGATIONS)

    change_a = tokens_a & CHANGE_WORDS
    change_b = tokens_b & CHANGE_WORDS

    if sem >= 0.70 and neg_a != neg_b:
        return (
            "CONTRADICTS",
            max(score, 0.55),
            (
                "The statements are semantically similar but "
                "assert opposite polarity through negation."
            ),
            signals,
        )

    if (
        sem >= 0.72
        and change_a
        and change_b
        and change_a != change_b
    ):
        return (
            "CONTRADICTS",
            max(score, 0.55),
            (
                "The statements describe the same topic but "
                "assert opposing change directions."
            ),
            signals,
        )

    if score >= 0.45:
        return (
            "RELATED",
            score,
            (
                "The statements are sufficiently related to "
                "inspect together, but the available evidence "
                "does not justify a stronger relationship."
            ),
            signals,
        )

    return (
        "UNRELATED",
        score,
        (
            "The statements do not contain enough shared "
            "evidence to establish a meaningful relationship."
        ),
        signals,
    )


def compare_facts(facts):
    if not facts:
        return []

    candidates = candidate_pairs(facts)

    if not candidates:
        return []

    matrix = build_similarity_matrix(facts)

    if matrix is None:
        return []

    results = []

    for i, j in candidates:
        a = facts[i]
        b = facts[j]

        sem = similarity_from_matrix(
            matrix,
            i,
            j
        )

        entities_a = normalized_entities(a)
        entities_b = normalized_entities(b)

        common_tokens = (
            meaningful_tokens(a.get("text", ""))
            &
            meaningful_tokens(b.get("text", ""))
        )

        # Keep numerical facts even when text similarity is weak.
        has_numbers = (
            numeric_value(a) is not None
            and numeric_value(b) is not None
        )

        has_subject_signal = same_subject_signal(a, b)

        if (
            sem < 0.12
            and not (entities_a & entities_b)
            and len(common_tokens) < 2
            and not has_subject_signal
            and not has_numbers
        ):
            continue

        relation_name, score, explanation, signals = relationship(
            a,
            b,
            sem=sem
        )

        if relation_name == "UNRELATED":
            continue

        # Strong benchmark relationships must survive even
        # when semantic similarity is not perfect.
        if (
            relation_name in {
                "CORROBORATES",
                "CONTRADICTS",
                "RECONCILES",
            }
            or score >= 0.42
        ):
            results.append(
                (
                    a["id"],
                    b["id"],
                    relation_name,
                    round(score, 4),
                    explanation,
                    json.dumps(signals),
                )
            )

    return results
