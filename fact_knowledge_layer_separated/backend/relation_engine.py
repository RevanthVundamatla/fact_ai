import json
import re
from collections import defaultdict
from itertools import combinations

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


# ============================================================
# VOCABULARY
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
    "were not",
    "was not",
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
    "growth",
    "decline",
    "increase",
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
    "reported",
    "according",
    "estimated",
    "respectively",
    "per",
    "cent",
    "percent",
    "from",
    "its",
    "our",
    "also",
    "more",
    "less",
    "approximately",
    "around",
}

# Concepts that should be treated as separate numerical topics.
TOPIC_GROUPS = {
    "revenue": {
        "revenue",
        "revenues",
        "income",
        "sales",
        "turnover",
        "services",
        "service",
    },
    "gdp": {
        "gdp",
        "growth",
        "economic",
        "economy",
        "output",
    },
    "employees": {
        "employee",
        "employees",
        "workforce",
        "workforce",
        "team",
        "staff",
        "headcount",
    },
    "mobility": {
        "mobility",
        "internal",
        "role",
        "roles",
        "transfer",
        "transferred",
        "movement",
    },
    "promotion": {
        "promotion",
        "promoted",
        "promotions",
    },
    "pin_codes": {
        "pin",
        "pincode",
        "pincodes",
        "codes",
        "postal",
    },
    "customers": {
        "customer",
        "customers",
        "client",
        "clients",
    },
    "facilities": {
        "facility",
        "facilities",
        "centre",
        "centres",
        "center",
        "centers",
    },
    "parcels": {
        "parcel",
        "parcels",
        "shipment",
        "shipments",
    },
    "freight": {
        "freight",
        "tonnes",
        "tons",
        "ton",
    },
    "countries": {
        "country",
        "countries",
    },
}


# ============================================================
# BASIC HELPERS
# ============================================================

def safe_json_list(value):
    """
    Safely decode JSON arrays stored in SQLite.
    """
    if not value:
        return []

    if isinstance(value, list):
        return value

    try:
        parsed = json.loads(value)

        if isinstance(parsed, list):
            return parsed

    except (TypeError, json.JSONDecodeError):
        pass

    return []


def tokens(text):
    """
    Tokenize text into lowercase alphanumeric tokens.
    """
    return set(
        re.findall(
            r"[a-zA-Z][a-zA-Z0-9_-]+",
            (text or "").lower(),
        )
    )


def meaningful_tokens(text):
    """
    Remove common words so semantic/topic comparison
    focuses on useful content.
    """
    return tokens(text) - STOP_TOKENS - NEGATIONS


def normalized_entities(fact):
    """
    Return normalized entity names.
    """
    return {
        str(x).strip().lower()
        for x in safe_json_list(fact.get("entities"))
        if str(x).strip()
    }


def normalized_dates(fact):
    """
    Return normalized extracted dates/periods.
    """
    return {
        str(x).strip().lower()
        for x in safe_json_list(fact.get("dates"))
        if str(x).strip()
    }


def fact_text(fact):
    return (
        fact.get("text")
        or fact.get("evidence")
        or ""
    )


# ============================================================
# SEMANTIC SIMILARITY
# ============================================================

def build_similarity_matrix(facts):
    """
    Build one TF-IDF matrix for all facts.

    This is substantially faster than fitting a vectorizer
    separately for every pair.
    """
    if not facts:
        return None

    texts = [
        fact_text(fact)
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
    if matrix is None:
        return 0.0

    return float(
        cosine_similarity(
            matrix[i],
            matrix[j],
        )[0, 0]
    )


# ============================================================
# NUMERICAL HELPERS
# ============================================================

def numeric_value(fact):
    """
    Use the normalized numeric value generated by the extractor.
    """
    value = fact.get("normalized_value")

    if value is None:
        value = fact.get("value")

    if value is None:
        return None

    try:
        return float(value)

    except (TypeError, ValueError):
        return None


def unit(fact):
    value = (
        fact.get("normalized_unit")
        or fact.get("unit")
        or ""
    )

    return str(value).strip().lower()


def canonical_unit(value):
    """
    Normalize common unit spellings.
    """
    value = str(value or "").strip().lower()

    aliases = {
        "mn": "million",
        "m": "million",
        "million": "million",
        "millions": "million",
        "₹ million": "million",
        "rs million": "million",
        "inr million": "million",
        "₹mn": "million",

        "cr": "crore",
        "crore": "crore",
        "crores": "crore",
        "₹ crore": "crore",
        "rs crore": "crore",
        "inr crore": "crore",
        "₹cr": "crore",

        "%": "percent",
        "percentage": "percent",
        "percent": "percent",
    }

    return aliases.get(value, value)


def convert_value(value, from_unit, to_unit):
    """
    Convert common financial units.

    1 crore = 10 million.
    """
    if value is None:
        return None

    from_unit = canonical_unit(from_unit)
    to_unit = canonical_unit(to_unit)

    if not from_unit or not to_unit:
        return None

    if from_unit == to_unit:
        return value

    if from_unit == "million" and to_unit == "crore":
        return value / 10.0

    if from_unit == "crore" and to_unit == "million":
        return value * 10.0

    return None


def direct_numeric_difference(a, b):
    """
    Compare two values if their canonical units match.
    """
    av = numeric_value(a)
    bv = numeric_value(b)

    if av is None or bv is None:
        return None

    ua = canonical_unit(unit(a))
    ub = canonical_unit(unit(b))

    if not ua or not ub or ua != ub:
        return None

    denominator = max(
        abs(av),
        abs(bv),
        1e-9,
    )

    return min(
        abs(av - bv) / denominator,
        1.0,
    )


def cross_unit_difference(a, b):
    """
    Compare values after converting compatible units.

    Example:

        81,415 million
        8,142 crore

    becomes:

        8,141.5 crore
        8,142 crore

    Difference ≈ 0.006%.
    """
    av = numeric_value(a)
    bv = numeric_value(b)

    if av is None or bv is None:
        return None, None

    ua = canonical_unit(unit(a))
    ub = canonical_unit(unit(b))

    if not ua or not ub:
        return None, None

    if ua == ub:
        denominator = max(
            abs(av),
            abs(bv),
            1e-9,
        )

        return (
            min(
                abs(av - bv) / denominator,
                1.0,
            ),
            None,
        )

    converted_a = convert_value(
        av,
        ua,
        ub,
    )

    if converted_a is not None:
        denominator = max(
            abs(converted_a),
            abs(bv),
            1e-9,
        )

        return (
            min(
                abs(converted_a - bv) / denominator,
                1.0,
            ),
            {
                "conversion": f"{ua} -> {ub}",
                "converted_value_a": round(
                    converted_a,
                    6,
                ),
            },
        )

    converted_b = convert_value(
        bv,
        ub,
        ua,
    )

    if converted_b is not None:
        denominator = max(
            abs(av),
            abs(converted_b),
            1e-9,
        )

        return (
            min(
                abs(av - converted_b) / denominator,
                1.0,
            ),
            {
                "conversion": f"{ub} -> {ua}",
                "converted_value_b": round(
                    converted_b,
                    6,
                ),
            },
        )

    return None, None


# ============================================================
# TIME / PERIOD ANALYSIS
# ============================================================

def period_scope(fact):
    """
    Identify broad temporal scope.

    Examples:
        Q1 FY25        -> quarter
        Q2 FY25        -> quarter
        H1 FY25        -> half-year
        FY2024/25      -> fiscal-year
        FY25           -> fiscal-year
        2024           -> year
    """
    text = fact_text(fact).lower()

    scopes = set()

    if re.search(
        r"\bq[1-4]\b",
        text,
    ):
        scopes.add("quarter")

    if re.search(
        r"\b(first|second|third|fourth)\s+quarter\b",
        text,
    ):
        scopes.add("quarter")

    if re.search(
        r"\b(?:h1|h2)\b|\bhalf[- ]year\b",
        text,
    ):
        scopes.add("half-year")

    if re.search(
        r"\bfy\s*20\d{2}(?:/\d{2,4})?\b",
        text,
    ):
        scopes.add("fiscal-year")

    if re.search(
        r"\b20\d{2}/\d{2,4}\b",
        text,
    ):
        scopes.add("fiscal-year")

    # A plain year should only be added if it wasn't already
    # classified as a fiscal year.
    if (
        "fiscal-year" not in scopes
        and re.search(r"\b20\d{2}\b", text)
    ):
        scopes.add("year")

    return scopes


def fiscal_year_tokens(fact):
    """
    Extract year identifiers for additional context.
    """
    text = fact_text(fact).lower()

    years = set(
        re.findall(
            r"20\d{2}",
            text,
        )
    )

    for item in normalized_dates(fact):
        years.update(
            re.findall(
                r"20\d{2}",
                item,
            )
        )

    return years


def date_overlap(a, b):
    """
    Return:
        True  -> explicit overlap found
        False -> explicit dates differ
        None  -> insufficient temporal information
    """
    dates_a = normalized_dates(a)
    dates_b = normalized_dates(b)

    if not dates_a or not dates_b:
        return None

    if dates_a & dates_b:
        return True

    years_a = fiscal_year_tokens(a)
    years_b = fiscal_year_tokens(b)

    if years_a & years_b:
        return True

    return False


def different_time_scope(a, b):
    """
    Detect when two facts measure different temporal scopes.

    This is critical for:
        Q1 vs FY
        Q2 vs FY
        H1 vs FY
    """
    text_a = fact_text(a).lower()
    text_b = fact_text(b).lower()

    scope_a = period_scope(a)
    scope_b = period_scope(b)

    # Explicit quarter vs annual.
    quarter_a = bool(
        re.search(r"\bq[1-4]\b", text_a)
    )

    quarter_b = bool(
        re.search(r"\bq[1-4]\b", text_b)
    )

    annual_a = bool(
        re.search(
            r"\bfy\s*20\d{2}(?:/\d{2,4})?\b"
            r"|\b20\d{2}/\d{2,4}\b",
            text_a,
        )
    )

    annual_b = bool(
        re.search(
            r"\bfy\s*20\d{2}(?:/\d{2,4})?\b"
            r"|\b20\d{2}/\d{2,4}\b",
            text_b,
        )
    )

    if (
        (quarter_a and annual_b)
        or
        (quarter_b and annual_a)
    ):
        return True

    # Half-year vs annual.
    half_a = bool(
        re.search(
            r"\b(?:h1|h2)\b|half[- ]year",
            text_a,
        )
    )

    half_b = bool(
        re.search(
            r"\b(?:h1|h2)\b|half[- ]year",
            text_b,
        )
    )

    if (
        (half_a and annual_b)
        or
        (half_b and annual_a)
    ):
        return True

    # If both scopes exist and are explicitly different.
    if (
        scope_a
        and scope_b
        and scope_a != scope_b
    ):
        return True

    return False


# ============================================================
# TOPIC / PREDICATE ANALYSIS
# ============================================================

def topic_signatures(fact):
    """
    Determine the semantic topic of a fact.

    This prevents:

        1,509 employees moved internally
        423 employees were promoted

    from being treated as a numerical contradiction.

    Both mention employees, but they belong to different
    topic groups: mobility vs promotion.
    """
    text_tokens = meaningful_tokens(
        fact_text(fact)
    )

    topics = set()

    for topic, vocabulary in TOPIC_GROUPS.items():

        if text_tokens & vocabulary:
            topics.add(topic)

    predicate = str(
        fact.get("predicate")
        or ""
    ).lower()

    if "mobility" in predicate:
        topics.add("mobility")

    if "promotion" in predicate:
        topics.add("promotion")

    if "revenue" in predicate:
        topics.add("revenue")

    if "gdp" in predicate:
        topics.add("gdp")

    return topics


def topics_compatible(a, b):
    """
    Decide whether two facts describe the same measurable topic.

    Returns:
        True   -> compatible/same topic
        False  -> clearly different topics
        None   -> uncertain
    """
    topics_a = topic_signatures(a)
    topics_b = topic_signatures(b)

    if not topics_a or not topics_b:
        return None

    # Explicitly different concepts.
    incompatible_pairs = {
        frozenset({"mobility", "promotion"}),
        frozenset({"mobility", "revenue"}),
        frozenset({"promotion", "revenue"}),
        frozenset({"customers", "employees"}),
        frozenset({"facilities", "employees"}),
        frozenset({"parcels", "employees"}),
        frozenset({"freight", "employees"}),
    }

    for ta in topics_a:
        for tb in topics_b:

            if frozenset({ta, tb}) in incompatible_pairs:
                return False

    # Shared topic.
    if topics_a & topics_b:
        return True

    # Different explicit topics.
    if len(topics_a) == 1 and len(topics_b) == 1:
        return False

    return None


def same_subject_signal(a, b):
    """
    Determine whether two facts plausibly refer to the same subject.
    """
    entities_a = normalized_entities(a)
    entities_b = normalized_entities(b)

    if entities_a & entities_b:
        return True

    topic_result = topics_compatible(a, b)

    if topic_result is True:
        return True

    text_a = meaningful_tokens(
        fact_text(a)
    )

    text_b = meaningful_tokens(
        fact_text(b)
    )

    shared = text_a & text_b

    important = {
        "revenue",
        "revenues",
        "services",
        "gdp",
        "growth",
        "employees",
        "workforce",
        "pin",
        "codes",
        "customers",
        "facilities",
        "parcels",
        "freight",
        "mobility",
        "promotion",
        "promoted",
    }

    return bool(
        shared & important
    )


# ============================================================
# CANDIDATE GENERATION
# ============================================================

def candidate_pairs(facts):
    """
    Generate plausible cross-document pairs.

    We intentionally do NOT require identical units because
    units such as million and crore may differ.

    We also avoid comparing facts from the same document.
    """
    if not facts:
        return []

    buckets = defaultdict(set)

    for index, fact in enumerate(facts):

        entities = normalized_entities(fact)

        text_tokens = meaningful_tokens(
            fact_text(fact)
        )

        topics = topic_signatures(fact)

        # Entity buckets.
        for entity in entities:
            buckets[
                ("entity", entity)
            ].add(index)

        # Topic buckets.
        for topic in topics:
            buckets[
                ("topic", topic)
            ].add(index)

        # Useful lexical buckets.
        for token in text_tokens:

            if len(token) >= 4:
                buckets[
                    ("token", token)
                ].add(index)

    pairs = set()

    for group in buckets.values():

        if len(group) < 2:
            continue

        # Avoid pathological generic buckets.
        if len(group) > 200:
            continue

        for i, j in combinations(
            sorted(group),
            2,
        ):

            a = facts[i]
            b = facts[j]

            # Never create cross-fact relationships inside
            # the same source document.
            if (
                a.get("document_id")
                ==
                b.get("document_id")
            ):
                continue

            pairs.add(
                (i, j)
            )

    return list(pairs)


# ============================================================
# SEMANTIC CONTRADICTION HELPERS
# ============================================================

def contains_negation(text):
    text = (text or "").lower()

    for negation in NEGATIONS:

        if negation in text:
            return True

    return False


def change_direction(text):
    """
    Return:
        positive
        negative
        None
    """
    text = (text or "").lower()

    positive = {
        "increased",
        "grew",
        "rose",
        "growth",
        "increase",
        "higher",
    }

    negative = {
        "decreased",
        "declined",
        "fell",
        "reduced",
        "dropped",
        "decline",
        "decrease",
        "lower",
    }

    has_positive = any(
        word in text
        for word in positive
    )

    has_negative = any(
        word in text
        for word in negative
    )

    if has_positive and not has_negative:
        return "positive"

    if has_negative and not has_positive:
        return "negative"

    return None


# ============================================================
# RELATIONSHIP CLASSIFICATION
# ============================================================

def relationship(a, b, sem=None):
    """
    Classify one pair of facts.

    Possible relations:

        CORROBORATES
        CONTRADICTS
        RECONCILES
        RELATED
        UNRELATED
    """

    if sem is None:

        matrix = build_similarity_matrix(
            [a, b]
        )

        sem = (
            similarity_from_matrix(
                matrix,
                0,
                1,
            )
            if matrix is not None
            else 0.0
        )

    entities_a = normalized_entities(a)
    entities_b = normalized_entities(b)

    entity_intersection = (
        entities_a & entities_b
    )

    entity_union = (
        entities_a | entities_b
    )

    entity_overlap = (
        len(entity_intersection)
        /
        max(
            1,
            len(entity_union),
        )
    )

    tokens_a = meaningful_tokens(
        fact_text(a)
    )

    tokens_b = meaningful_tokens(
        fact_text(b)
    )

    common_tokens = (
        tokens_a & tokens_b
    )

    meaningful_overlap = len(
        common_tokens
    )

    subject_signal = same_subject_signal(
        a,
        b,
    )

    topic_result = topics_compatible(
        a,
        b,
    )

    time_scope_diff = different_time_scope(
        a,
        b,
    )

    dates_overlap = date_overlap(
        a,
        b,
    )

    same_unit = (
        bool(unit(a))
        and bool(unit(b))
        and canonical_unit(unit(a))
        ==
        canonical_unit(unit(b))
    )

    direct_difference = direct_numeric_difference(
        a,
        b,
    )

    converted_difference, conversion_info = (
        cross_unit_difference(
            a,
            b,
        )
    )

    numeric_diff = (
        direct_difference
        if direct_difference is not None
        else converted_difference
    )

    # --------------------------------------------------------
    # Base score
    # --------------------------------------------------------

    score = (
        0.40 * sem
        + 0.20 * entity_overlap
        + 0.15 * min(
            meaningful_overlap / 6.0,
            1.0,
        )
        + 0.15 * (
            1.0
            if subject_signal
            else 0.0
        )
        + 0.10 * (
            1.0
            if topic_result is True
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

        "shared_entities": sorted(
            entity_intersection
        ),

        "meaningful_token_overlap": (
            meaningful_overlap
        ),

        "shared_tokens": sorted(
            common_tokens
        )[:20],

        "subject_signal": (
            subject_signal
        ),

        "topic_a": sorted(
            topic_signatures(a)
        ),

        "topic_b": sorted(
            topic_signatures(b)
        ),

        "topics_compatible": (
            topic_result
        ),

        "normalized_unit_match": (
            same_unit
        ),

        "unit_a": canonical_unit(
            unit(a)
        ),

        "unit_b": canonical_unit(
            unit(b)
        ),

        "relative_numeric_difference": (
            None
            if numeric_diff is None
            else round(
                numeric_diff,
                6,
            )
        ),

        "date_overlap": (
            dates_overlap
        ),

        "different_time_scope": (
            time_scope_diff
        ),

        "conversion": (
            conversion_info
        ),
    }

    # ========================================================
    # IMPORTANT SAFETY RULE
    # ========================================================
    #
    # If two numerical facts clearly describe different
    # semantic topics, DO NOT call them contradictions.
    #
    # This handles the required failure case:
    #
    # 1,509 internal mobility
    # 423 promotions
    #
    # Both concern employees, but they measure different things.
    # ========================================================

    if (
        numeric_diff is not None
        and topic_result is False
    ):

        return (
            "RELATED",
            min(
                score,
                0.49,
            ),
            (
                "The statements contain numerical values and "
                "share some broad subject context, but they "
                "measure different semantic topics. They are "
                "therefore not treated as a contradiction."
            ),
            signals,
        )

    # ========================================================
    # NUMERICAL RELATIONSHIPS
    # ========================================================

    if numeric_diff is not None:

        # ----------------------------------------------------
        # CORROBORATION
        # ----------------------------------------------------
        #
        # Near identical values after unit normalization.
        # Example:
        #
        # 81,415 million
        # 8,142 crore
        #
        # 81,415 / 10 = 8,141.5 crore
        #
        # Difference is ~0.006%.
        # ----------------------------------------------------

        if (
            numeric_diff <= 0.02
            and not time_scope_diff
            and (
                topic_result is not False
            )
        ):

            if conversion_info:

                conversion_text = (
                    " Unit conversion was applied: "
                    f"{conversion_info['conversion']}."
                )

            else:

                conversion_text = ""

            return (
                "CORROBORATES",
                max(
                    score,
                    0.75,
                ),
                (
                    "The statements describe the same "
                    "measurable fact and their values agree "
                    "after normalization."
                    f"{conversion_text} "
                    "The remaining difference is small enough "
                    "to be explained by rounding or display "
                    "precision."
                ),
                signals,
            )

        # ----------------------------------------------------
        # CONTEXTUAL RECONCILIATION
        # ----------------------------------------------------
        #
        # Different scopes such as:
        #
        # Q1 6.7%
        # Q2 5.4%
        # FY25 6.4%
        #
        # should not be called contradictions.
        # ----------------------------------------------------

        if (
            time_scope_diff
            and topic_result is not False
        ):

            return (
                "RECONCILES",
                max(
                    score,
                    0.60,
                ),
                (
                    "The numerical values refer to different "
                    "time scopes or reporting periods. They "
                    "therefore describe different measurements "
                    "rather than directly conflicting claims."
                ),
                signals,
            )

        # ----------------------------------------------------
        # SMALL DIFFERENCE
        # ----------------------------------------------------

        if numeric_diff < 0.10:

            return (
                "RELATED",
                score,
                (
                    "The statements concern a similar "
                    "measurable fact, but the numerical "
                    "difference is too large for confident "
                    "corroboration and too small to establish "
                    "a strong contradiction."
                ),
                signals,
            )

        # ----------------------------------------------------
        # MATERIAL DIFFERENCE
        # ----------------------------------------------------

        if (
            numeric_diff >= 0.10
            and topic_result is not False
        ):

            return (
                "CONTRADICTS",
                max(
                    score,
                    0.55,
                ),
                (
                    "The statements appear to describe the "
                    "same measurable topic in comparable "
                    "units and reporting scope, but their "
                    "normalized values differ materially."
                ),
                signals,
            )

    # ========================================================
    # SEMANTIC RELATIONSHIPS
    # ========================================================

    neg_a = contains_negation(
        fact_text(a)
    )

    neg_b = contains_negation(
        fact_text(b)
    )

    # Opposite polarity.
    if (
        sem >= 0.70
        and neg_a != neg_b
        and topic_result is not False
    ):

        return (
            "CONTRADICTS",
            max(
                score,
                0.55,
            ),
            (
                "The statements are semantically similar "
                "but assert opposite polarity through "
                "negation."
            ),
            signals,
        )

    direction_a = change_direction(
        fact_text(a)
    )

    direction_b = change_direction(
        fact_text(b)
    )

    if (
        sem >= 0.72
        and direction_a
        and direction_b
        and direction_a != direction_b
        and topic_result is not False
    ):

        return (
            "CONTRADICTS",
            max(
                score,
                0.55,
            ),
            (
                "The statements describe the same topic "
                "but assert opposing directions of change."
            ),
            signals,
        )

    # --------------------------------------------------------
    # Related semantic facts.
    # --------------------------------------------------------

    if score >= 0.45:

        return (
            "RELATED",
            score,
            (
                "The statements are sufficiently related "
                "to inspect together, but the available "
                "evidence does not justify a stronger "
                "relationship."
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


# ============================================================
# COMPARE ALL FACTS
# ============================================================

def compare_facts(facts):
    """
    Compare extracted facts across documents.

    Returns tuples:

        (
            fact_a_id,
            fact_b_id,
            relation,
            score,
            explanation,
            signals_json
        )
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

    results = []

    for i, j in candidates:

        a = facts[i]
        b = facts[j]

        sem = similarity_from_matrix(
            matrix,
            i,
            j,
        )

        entities_a = normalized_entities(
            a
        )

        entities_b = normalized_entities(
            b
        )

        common_tokens = (
            meaningful_tokens(
                fact_text(a)
            )
            &
            meaningful_tokens(
                fact_text(b)
            )
        )

        has_numbers = (
            numeric_value(a) is not None
            and
            numeric_value(b) is not None
        )

        has_subject_signal = (
            same_subject_signal(
                a,
                b,
            )
        )

        topic_result = topics_compatible(
            a,
            b,
        )

        # ----------------------------------------------------
        # Reject obviously unrelated semantic pairs.
        # ----------------------------------------------------

        if (
            sem < 0.12
            and not (
                entities_a
                &
                entities_b
            )
            and len(common_tokens) < 2
            and not has_subject_signal
            and not has_numbers
        ):
            continue

        relation_name, score, explanation, signals = (
            relationship(
                a,
                b,
                sem=sem,
            )
        )

        if relation_name == "UNRELATED":
            continue

        # ----------------------------------------------------
        # Strong relations are always retained.
        # ----------------------------------------------------

        if relation_name in {
            "CORROBORATES",
            "CONTRADICTS",
            "RECONCILES",
        }:

            results.append(
                (
                    a["id"],
                    b["id"],
                    relation_name,
                    round(
                        score,
                        4,
                    ),
                    explanation,
                    json.dumps(
                        signals
                    ),
                )
            )

            continue

        # ----------------------------------------------------
        # Keep useful RELATED relationships, but don't flood
        # the UI with weak relationships.
        # ----------------------------------------------------

        if score >= 0.45:

            results.append(
                (
                    a["id"],
                    b["id"],
                    relation_name,
                    round(
                        score,
                        4,
                    ),
                    explanation,
                    json.dumps(
                        signals
                    ),
                )
            )

    # Highest-confidence relationships first.
    results.sort(
        key=lambda x: x[3],
        reverse=True,
    )

    return results
