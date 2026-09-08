import json
import re
from collections import defaultdict
from itertools import combinations

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


NEGATIONS = {
    "not",
    "no",
    "never",
    "none",
    "without",
    "didn't",
    "doesn't",
    "isn't",
    "wasn't",
}

CHANGE_WORDS = {
    "increased",
    "decreased",
    "grew",
    "declined",
    "rose",
    "fell",
    "reduced",
    "dropped",
}

# Common words that are not useful for candidate matching.
STOP_TOKENS = {
    "the",
    "and",
    "for",
    "from",
    "with",
    "that",
    "this",
    "were",
    "was",
    "are",
    "has",
    "have",
    "had",
    "into",
    "than",
    "then",
    "their",
    "there",
    "about",
    "during",
    "through",
    "under",
    "over",
    "year",
    "years",
    "period",
    "ended",
    "ending",
}


def safe_json_list(value):
    """
    Safely parse a JSON list stored in the database.
    """
    if not value:
        return []

    try:
        parsed = json.loads(value)

        if isinstance(parsed, list):
            return parsed

    except (TypeError, json.JSONDecodeError):
        pass

    return []


def tokens(s):
    """
    Convert text into normalized tokens.
    """
    return set(
        re.findall(
            r"[a-zA-Z][a-zA-Z0-9_-]+",
            (s or "").lower(),
        )
    )


def meaningful_tokens(s):
    """
    Remove generic words so candidate matching is more useful.
    """
    return tokens(s) - STOP_TOKENS - NEGATIONS


def similarity_from_matrix(matrix, i, j):
    """
    Calculate cosine similarity using a pre-built TF-IDF matrix.

    This is much faster than creating a new TfidfVectorizer
    for every fact pair.
    """
    return float(cosine_similarity(matrix[i], matrix[j])[0, 0])


def build_similarity_matrix(facts):
    """
    Build ONE TF-IDF matrix for all facts.

    Old implementation:
        TfidfVectorizer() -> fit_transform([a, b])
        for every pair.

    New implementation:
        One vectorizer -> one matrix.
    """
    if not facts:
        return None

    texts = [fact.get("text", "") or "" for fact in facts]

    vectorizer = TfidfVectorizer(
        ngram_range=(1, 2),
        stop_words="english",
        max_features=20000,
        dtype=float,
    )

    try:
        return vectorizer.fit_transform(texts)
    except ValueError:
        # Happens if all texts are empty.
        return None


def candidate_pairs(facts):
    """
    Generate only likely fact pairs.

    Instead of:

        N facts -> N*(N-1)/2 comparisons

    we first bucket facts by:
        - entity
        - normalized unit
        - meaningful text tokens

    This dramatically reduces the number of expensive comparisons.
    """

    if not facts:
        return []

    buckets = defaultdict(set)

    for index, fact in enumerate(facts):
        document_id = fact.get("document_id")

        entities = {
            str(x).strip().lower()
            for x in safe_json_list(fact.get("entities"))
            if str(x).strip()
        }

        unit = (
            str(fact.get("normalized_unit") or "")
            .strip()
            .lower()
        )

        text_tokens = meaningful_tokens(fact.get("text", ""))

        # Strong signal: shared entity + unit.
        for entity in entities:
            buckets[("entity", entity, unit)].add(index)

            # Also create an entity-only bucket.
            buckets[("entity_only", entity)].add(index)

        # Useful fallback for facts without entities.
        for token in text_tokens:
            if len(token) >= 4:
                buckets[("token", token)].add(index)

    pairs = set()

    for group in buckets.values():
        if len(group) < 2:
            continue

        # Avoid huge buckets created by generic terms.
        if len(group) > 100:
            continue

        for i, j in combinations(sorted(group), 2):
            a = facts[i]
            b = facts[j]

            # Never compare facts from the same document.
            if a.get("document_id") == b.get("document_id"):
                continue

            pairs.add((i, j))

    return list(pairs)


def relationship(a, b, sem=None):
    """
    Determine the relationship between two facts.

    `sem` can be supplied by compare_facts() so we don't
    repeatedly calculate TF-IDF similarity.
    """

    if sem is None:
        # Fallback for callers that directly use relationship().
        matrix = build_similarity_matrix([a, b])

        if matrix is None:
            sem = 0.0
        else:
            sem = similarity_from_matrix(matrix, 0, 1)

    entities_a = {
        str(x).strip().lower()
        for x in safe_json_list(a.get("entities"))
        if str(x).strip()
    }

    entities_b = {
        str(x).strip().lower()
        for x in safe_json_list(b.get("entities"))
        if str(x).strip()
    }

    entity_overlap = len(entities_a & entities_b) / max(
        1,
        len(entities_a | entities_b),
    )

    unit_a = (
        str(a.get("normalized_unit") or "")
        .strip()
        .lower()
    )

    unit_b = (
        str(b.get("normalized_unit") or "")
        .strip()
        .lower()
    )

    same_unit = bool(
        unit_a
        and unit_b
        and unit_a == unit_b
    )

    numeric = None

    value_a = a.get("normalized_value")
    value_b = b.get("normalized_value")

    if (
        value_a is not None
        and value_b is not None
        and same_unit
    ):
        try:
            av = float(value_a)
            bv = float(value_b)

            denominator = max(
                abs(av),
                abs(bv),
                1e-9,
            )

            numeric = min(
                abs(av - bv) / denominator,
                1.0,
            )

        except (TypeError, ValueError):
            numeric = None

    dates_a = {
        str(x).strip().lower()
        for x in safe_json_list(a.get("dates"))
        if str(x).strip()
    }

    dates_b = {
        str(x).strip().lower()
        for x in safe_json_list(b.get("dates"))
        if str(x).strip()
    }

    date_overlap = (
        len(dates_a & dates_b) > 0
        if dates_a and dates_b
        else None
    )

    period_types = {
        "quarter",
        "year",
        "month",
        "day",
        "week",
        "half-year",
        "half",
    }

    period_a = dates_a & period_types
    period_b = dates_b & period_types

    different_period = bool(
        period_a
        and period_b
        and period_a != period_b
    )

    common = meaningful_tokens(
        a.get("text", "")
    ) & meaningful_tokens(
        b.get("text", "")
    )

    meaningful_overlap = len(common) >= 3

    score = (
        0.55 * sem
        + 0.30 * entity_overlap
        + 0.15 * (
            1.0 if meaningful_overlap else 0.0
        )
    )

    signals = {
        "semantic_similarity": round(sem, 3),
        "entity_overlap": round(entity_overlap, 3),
        "normalized_unit_match": bool(same_unit),
        "relative_numeric_difference": (
            None
            if numeric is None
            else round(numeric, 3)
        ),
        "date_overlap": date_overlap,
        "different_period_type": different_period,
    }

    # Very weak relationship.
    if score < 0.30:
        return (
            "RELATED",
            score,
            (
                "The statements have limited "
                "semantic/entity overlap; they are "
                "retained as related rather than "
                "forced into a stronger relationship."
            ),
            signals,
        )

    # Numerical reasoning.
    if numeric is not None:

        # Almost identical normalized values.
        if numeric <= 0.02 and date_overlap is not False:
            return (
                "CORROBORATES",
                score,
                (
                    "The statements refer to a "
                    "compatible measurement after "
                    "unit normalization, with "
                    "overlapping or unspecified "
                    "time context."
                ),
                signals,
            )

        # Different periods explain the difference.
        if different_period or date_overlap is False:
            return (
                "RECONCILES",
                score,
                (
                    "The measurements differ, but "
                    "the evidence indicates different "
                    "time-period scopes, so the values "
                    "need not conflict."
                ),
                signals,
            )

        # Material numerical difference.
        if numeric >= 0.10:
            return (
                "CONTRADICTS",
                score,
                (
                    "Both statements describe a similar "
                    "measurable fact in compatible units, "
                    "but their normalized values materially "
                    "disagree."
                ),
                signals,
            )

    # Semantic contradiction heuristics.
    tokens_a = tokens(a.get("text", ""))
    tokens_b = tokens(b.get("text", ""))

    neg_a = bool(tokens_a & NEGATIONS)
    neg_b = bool(tokens_b & NEGATIONS)

    change_a = tokens_a & CHANGE_WORDS
    change_b = tokens_b & CHANGE_WORDS

    if sem >= 0.62 and neg_a != neg_b:
        return (
            "CONTRADICTS",
            score,
            (
                "The statements are semantically "
                "similar but differ in polarity/"
                "negation."
            ),
            signals,
        )

    if (
        sem >= 0.70
        and change_a
        and change_b
        and change_a != change_b
    ):
        return (
            "CONTRADICTS",
            score,
            (
                "The statements describe the same "
                "topic but assert opposing change "
                "directions."
            ),
            signals,
        )

    return (
        "RELATED",
        score,
        (
            "The statements are sufficiently similar "
            "to inspect together, but the available "
            "evidence is not strong enough to label "
            "them corroborating or contradictory."
        ),
        signals,
    )


def compare_facts(facts):
    """
    Compare facts efficiently.

    Performance improvements:
        1. Candidate filtering before similarity.
        2. One TF-IDF matrix for all facts.
        3. No same-document comparisons.
        4. Similarity calculated only for candidate pairs.
    """

    if not facts:
        return []

    # ---------------------------------------------------------
    # STEP 1: Find realistic candidate pairs.
    # ---------------------------------------------------------

    candidates = candidate_pairs(facts)

    if not candidates:
        return []

    # ---------------------------------------------------------
    # STEP 2: Build TF-IDF ONCE.
    # ---------------------------------------------------------

    matrix = build_similarity_matrix(facts)

    if matrix is None:
        return []

    # ---------------------------------------------------------
    # STEP 3: Evaluate only candidates.
    # ---------------------------------------------------------

    pairs = []

    for i, j in candidates:
        a = facts[i]
        b = facts[j]

        sem = similarity_from_matrix(
            matrix,
            i,
            j,
        )

        # Cheap early filter.
        #
        # If semantic similarity is extremely low
        # and there are no shared entities, there is
        # little reason to run the full reasoning.
        entities_a = {
            str(x).strip().lower()
            for x in safe_json_list(a.get("entities"))
            if str(x).strip()
        }

        entities_b = {
            str(x).strip().lower()
            for x in safe_json_list(b.get("entities"))
            if str(x).strip()
        }

        shared_entities = entities_a & entities_b

        common_tokens = (
            meaningful_tokens(a.get("text", ""))
            & meaningful_tokens(b.get("text", ""))
        )

        if (
            sem < 0.20
            and not shared_entities
            and len(common_tokens) < 3
        ):
            continue

        relation_name, score, explanation, signals = relationship(
            a,
            b,
            sem=sem,
        )

        # Keep strong relationships and useful related facts.
        if (
            relation_name
            in {
                "CORROBORATES",
                "CONTRADICTS",
                "RECONCILES",
            }
            or score >= 0.48
        ):
            pairs.append(
                (
                    a["id"],
                    b["id"],
                    relation_name,
                    score,
                    explanation,
                    json.dumps(signals),
                )
            )

    return pairs
