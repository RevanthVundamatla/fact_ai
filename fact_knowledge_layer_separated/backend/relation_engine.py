import json
import re
from collections import defaultdict
from itertools import combinations

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


# ============================================================
# CONSTANTS
# ============================================================

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


# ============================================================
# JSON HELPERS
# ============================================================

def safe_json_list(value):
    """
    Safely parse a JSON list stored in SQLite.
    """

    if not value:
        return []

    try:
        parsed = json.loads(value)

        if isinstance(parsed, list):
            return parsed

    except (
        TypeError,
        json.JSONDecodeError,
    ):
        pass

    return []


# ============================================================
# TOKENIZATION
# ============================================================

def tokens(text):
    """
    Normalize text into tokens.
    """

    return set(
        re.findall(
            r"[a-zA-Z][a-zA-Z0-9_-]+",
            (text or "").lower(),
        )
    )


def meaningful_tokens(text):
    """
    Remove generic words.
    """

    return (
        tokens(text)
        - STOP_TOKENS
        - NEGATIONS
    )


# ============================================================
# TF-IDF
# ============================================================

def build_similarity_matrix(facts):
    """
    Build one TF-IDF matrix for all facts.

    This is significantly faster than fitting a new
    vectorizer for every pair.
    """

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
    """
    Calculate cosine similarity from a pre-built matrix.
    """

    return float(
        cosine_similarity(
            matrix[i],
            matrix[j],
        )[0, 0]
    )


# ============================================================
# CANDIDATE GENERATION
# ============================================================

def candidate_pairs(facts):
    """
    Generate likely cross-document fact pairs.

    Candidate signals:
        - shared entity
        - shared entity + unit
        - shared meaningful token

    Same-document facts are never compared.
    """

    if not facts:
        return []

    buckets = defaultdict(set)

    for index, fact in enumerate(facts):

        entities = {
            str(value).strip().lower()
            for value in safe_json_list(
                fact.get("entities")
            )
            if str(value).strip()
        }

        unit = (
            str(
                fact.get("normalized_unit")
                or ""
            )
            .strip()
            .lower()
        )

        text_tokens = meaningful_tokens(
            fact.get("text", "")
        )

        # ----------------------------------------------------
        # Entity buckets
        # ----------------------------------------------------

        for entity in entities:

            buckets[
                (
                    "entity",
                    entity,
                    unit,
                )
            ].add(index)

            buckets[
                (
                    "entity_only",
                    entity,
                )
            ].add(index)

        # ----------------------------------------------------
        # Token buckets
        # ----------------------------------------------------

        for token in text_tokens:

            if len(token) >= 4:

                buckets[
                    (
                        "token",
                        token,
                    )
                ].add(index)

    pairs = set()

    for group in buckets.values():

        if len(group) < 2:
            continue

        # Prevent generic tokens from creating huge
        # comparison groups.
        if len(group) > 100:
            continue

        for i, j in combinations(
            sorted(group),
            2,
        ):

            a = facts[i]
            b = facts[j]

            # Never compare facts inside the same PDF.
            if (
                a.get("document_id")
                == b.get("document_id")
            ):
                continue

            pairs.add((i, j))

    return list(pairs)


# ============================================================
# RELATIONSHIP REASONING
# ============================================================

def relationship(a, b, sem=None):
    """
    Determine the relationship between two facts.
    """

    if sem is None:

        matrix = build_similarity_matrix(
            [a, b]
        )

        if matrix is None:
            sem = 0.0
        else:
            sem = similarity_from_matrix(
                matrix,
                0,
                1,
            )

    entities_a = {
        str(value).strip().lower()
        for value in safe_json_list(
            a.get("entities")
        )
        if str(value).strip()
    }

    entities_b = {
        str(value).strip().lower()
        for value in safe_json_list(
            b.get("entities")
        )
        if str(value).strip()
    }

    entity_overlap = (
        len(entities_a & entities_b)
        / max(
            1,
            len(entities_a | entities_b),
        )
    )

    unit_a = (
        str(
            a.get("normalized_unit")
            or ""
        )
        .strip()
        .lower()
    )

    unit_b = (
        str(
            b.get("normalized_unit")
            or ""
        )
        .strip()
        .lower()
    )

    same_unit = bool(
        unit_a
        and unit_b
        and unit_a == unit_b
    )

    # --------------------------------------------------------
    # Numerical comparison
    # --------------------------------------------------------

    numeric_difference = None

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

            numeric_difference = min(
                abs(av - bv) / denominator,
                1.0,
            )

        except (
            TypeError,
            ValueError,
        ):
            numeric_difference = None

    # --------------------------------------------------------
    # Date comparison
    # --------------------------------------------------------

    dates_a = {
        str(value).strip().lower()
        for value in safe_json_list(
            a.get("dates")
        )
        if str(value).strip()
    }

    dates_b = {
        str(value).strip().lower()
        for value in safe_json_list(
            b.get("dates")
        )
        if str(value).strip()
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

    # --------------------------------------------------------
    # Text overlap
    # --------------------------------------------------------

    common_tokens = (
        meaningful_tokens(
            a.get("text", "")
        )
        &
        meaningful_tokens(
            b.get("text", "")
        )
    )

    meaningful_overlap = (
        len(common_tokens) >= 3
    )

    # --------------------------------------------------------
    # Overall score
    # --------------------------------------------------------

    score = (
        0.55 * sem
        + 0.30 * entity_overlap
        + 0.15 * (
            1.0
            if meaningful_overlap
            else 0.0
        )
    )

    signals = {
        "semantic_similarity": round(
            sem,
            3,
        ),
        "entity_overlap": round(
            entity_overlap,
            3,
        ),
        "normalized_unit_match": bool(
            same_unit
        ),
        "relative_numeric_difference": (
            None
            if numeric_difference is None
            else round(
                numeric_difference,
                3,
            )
        ),
        "date_overlap": date_overlap,
        "different_period_type": (
            different_period
        ),
    }

    # --------------------------------------------------------
    # Weak relationship
    # --------------------------------------------------------

    if score < 0.30:

        return (
            "RELATED",
            score,
            (
                "The statements have limited "
                "semantic or entity overlap; "
                "they are retained as related "
                "rather than forced into a "
                "stronger relationship."
            ),
            signals,
        )

    # --------------------------------------------------------
    # Numerical reasoning
    # --------------------------------------------------------

    if numeric_difference is not None:

        # Almost identical values.
        if (
            numeric_difference <= 0.02
            and date_overlap is not False
        ):

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

        # Different time scopes.
        if (
            different_period
            or date_overlap is False
        ):

            return (
                "RECONCILES",
                score,
                (
                    "The measurements differ, but "
                    "the evidence indicates "
                    "different time-period scopes, "
                    "so the values need not conflict."
                ),
                signals,
            )

        # Material disagreement.
        if numeric_difference >= 0.10:

            return (
                "CONTRADICTS",
                score,
                (
                    "Both statements describe a "
                    "similar measurable fact in "
                    "compatible units, but their "
                    "normalized values materially "
                    "disagree."
                ),
                signals,
            )

    # --------------------------------------------------------
    # Semantic contradiction
    # --------------------------------------------------------

    tokens_a = tokens(
        a.get("text", "")
    )

    tokens_b = tokens(
        b.get("text", "")
    )

    neg_a = bool(
        tokens_a & NEGATIONS
    )

    neg_b = bool(
        tokens_b & NEGATIONS
    )

    change_a = (
        tokens_a & CHANGE_WORDS
    )

    change_b = (
        tokens_b & CHANGE_WORDS
    )

    if (
        sem >= 0.62
        and neg_a != neg_b
    ):

        return (
            "CONTRADICTS",
            score,
            (
                "The statements are semantically "
                "similar but differ in "
                "polarity or negation."
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
                "The statements describe the "
                "same topic but assert opposing "
                "change directions."
            ),
            signals,
        )

    # --------------------------------------------------------
    # Default
    # --------------------------------------------------------

    return (
        "RELATED",
        score,
        (
            "The statements are sufficiently "
            "similar to inspect together, but "
            "the available evidence is not strong "
            "enough to label them corroborating "
            "or contradictory."
        ),
        signals,
    )


# ============================================================
# FACT COMPARISON
# ============================================================

def compare_facts(facts):
    """
    Efficiently compare facts.

    Pipeline:

        Facts
          ↓
        Candidate filtering
          ↓
        One TF-IDF matrix
          ↓
        Cheap similarity filtering
          ↓
        Relationship reasoning
    """

    if not facts:
        return []

    candidates = candidate_pairs(
        facts
    )

    if not candidates:
        return []

    matrix = build_similarity_matrix(
        facts
    )

    if matrix is None:
        return []

    pairs = []

    for i, j in candidates:

        a = facts[i]
        b = facts[j]

        sem = similarity_from_matrix(
            matrix,
            i,
            j,
        )

        entities_a = {
            str(value).strip().lower()
            for value in safe_json_list(
                a.get("entities")
            )
            if str(value).strip()
        }

        entities_b = {
            str(value).strip().lower()
            for value in safe_json_list(
                b.get("entities")
            )
            if str(value).strip()
        }

        shared_entities = (
            entities_a & entities_b
        )

        common_tokens = (
            meaningful_tokens(
                a.get("text", "")
            )
            &
            meaningful_tokens(
                b.get("text", "")
            )
        )

        # ----------------------------------------------------
        # Cheap early rejection
        # ----------------------------------------------------

        if (
            sem < 0.20
            and not shared_entities
            and len(common_tokens) < 3
        ):
            continue

        (
            relation_name,
            score,
            explanation,
            signals,
        ) = relationship(
            a,
            b,
            sem=sem,
        )

        # ----------------------------------------------------
        # Keep meaningful relationships
        # ----------------------------------------------------

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
                    json.dumps(
                        signals
                    ),
                )
            )

    return pairs
