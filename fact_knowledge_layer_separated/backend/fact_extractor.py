import re
from .models import CandidateFact
from .normalizer import (
    extract_dates,
    extract_period_tokens,
    extract_numeric,
)


# ---------------------------------------------------------------------------
# Common words that should not be treated as useful entities
# ---------------------------------------------------------------------------

STOP = {
    "the", "a", "an", "and", "or", "but", "was", "were", "is", "are",
    "has", "have", "had", "this", "that", "with", "from", "for", "in",
    "on", "of", "to", "by", "as", "at", "its", "their", "it", "company",
    "reported", "according", "during", "year", "years", "period", "ended",
    "ended", "quarter", "quarters", "month", "months", "million", "billion",
    "crore", "crores", "lakh", "lakhs", "per", "than", "more", "less",
    "approximately", "around", "about", "nearly", "over", "under",
}


# ---------------------------------------------------------------------------
# Words that usually indicate an actual factual/assertive statement
# ---------------------------------------------------------------------------

DECLARATIVE = re.compile(
    r"\b("
    r"is|are|was|were|be|been|being|"
    r"has|have|had|"
    r"reported|reports|reporting|"
    r"reached|reach|"
    r"recorded|records|"
    r"generated|generates|"
    r"earned|earns|"
    r"revenue|"
    r"operates|operated|"
    r"employs|employed|"
    r"acquired|acquires|"
    r"sold|sells|"
    r"increased|increases|"
    r"decreased|decreases|"
    r"grew|grows|growth|"
    r"declined|declines|"
    r"appointed|appoints|"
    r"resigned|resigns|"
    r"located|"
    r"produces|produced|"
    r"serves|served|"
    r"covers|covered|"
    r"serviced|service|"
    r"handles|handled|"
    r"processed|processes|"
    r"customers|customer|"
    r"employees|employee|"
    r"workforce|"
    r"facilities|facility|"
    r"centres|centers|"
    r"countries|country|"
    r"exports|imports|"
    r"accounts|"
    r"holds|held|"
    r"owns|owned|"
    r"invested|invests|"
    r"spent|spends|"
    r"costs|cost|"
    r"amounts|amount|"
    r"stands|"
    r"represents|represented|"
    r"constitutes|constituted|"
    r"accounts"
    r")\b",
    re.I,
)


# ---------------------------------------------------------------------------
# Numeric detection
#
# This is intentionally broad. The normalizer remains responsible for
# canonical conversion, while these patterns help decide whether a sentence
# actually contains a measurable claim.
# ---------------------------------------------------------------------------

NUMBER_RE = re.compile(
    r"""
    (?:
        (?<![\w])
        [+-]?
        (?:
            \d{1,3}(?:,\d{2,3})+(?:\.\d+)?
            |
            \d+(?:\.\d+)?
            |
            \.\d+
        )
        %?
        (?![\w])
    )
    """,
    re.VERBOSE,
)


# Currency symbols/codes frequently found in financial PDFs.
CURRENCY_RE = re.compile(
    r"(?:₹|\$|€|£|¥|USD|EUR|GBP|INR|JPY|Rs\.?|INR\.)",
    re.I,
)


# Useful measurement units. This is deliberately generic rather than
# document-specific.
UNIT_RE = re.compile(
    r"\b("
    r"%|percent|percentage|"
    r"million|billion|trillion|"
    r"crore|crores|lakh|lakhs|"
    r"thousand|"
    r"km|kms|kilomet(?:er|re)s?|"
    r"sq\.?\s*ft|sqft|square\s+feet|"
    r"kg|kgs|kilograms?|"
    r"tonnes?|tons?|"
    r"grams?|"
    r"hours?|minutes?|seconds?|"
    r"days?|weeks?|months?|years?|"
    r"employees?|customers?|"
    r"facilities?|cent(?:re|er)s?|"
    r"pin\s*codes?|"
    r"countries?|"
    r"parcels?|orders?|"
    r"units?|"
    r"points?|"
    r"times?"
    r")\b",
    re.I,
)


# ---------------------------------------------------------------------------
# Entity extraction
# ---------------------------------------------------------------------------

ENTITY_RE = re.compile(
    r"\b"
    r"(?:[A-Z][A-Za-z0-9&./'()-]*"
    r"(?:\s+[A-Z][A-Za-z0-9&./'()-]*){0,5})"
)


def entities(text):
    """
    Extract likely named entities from a sentence.

    This is intentionally heuristic and does not assume any particular
    company, country, PDF, schema, or vocabulary.
    """
    values = []

    for match in ENTITY_RE.findall(text):
        value = match.strip(" ,.;:()[]{}")

        if len(value) <= 1:
            continue

        if value.lower() in STOP:
            continue

        # Ignore obvious sentence starters that are not entities.
        if value.lower() in {
            "the", "this", "these", "those", "during", "according",
            "for", "from", "note", "source", "table", "figure",
        }:
            continue

        values.append(value)

    # Preserve order and remove duplicates.
    return list(dict.fromkeys(values))[:12]


# ---------------------------------------------------------------------------
# Subject extraction
# ---------------------------------------------------------------------------

def subject_guess(sentence):
    """
    Produce a lightweight subject candidate.

    This is not intended to be a full NLP parser. It gives the relationship
    engine useful lexical context without hardcoding a document schema.
    """

    sentence = re.sub(r"\s+", " ", sentence).strip()

    if not sentence:
        return None

    # Remove common introductory constructions.
    cleaned = re.sub(
        r"^(according to|as per|based on|during|in|for|as of)\b.*?,\s*",
        "",
        sentence,
        flags=re.I,
    ).strip()

    # Prefer a named-entity-like phrase if one exists.
    ents = entities(cleaned)

    if ents:
        return ents[0]

    # Otherwise keep a compact leading phrase.
    words = cleaned.split()

    if not words:
        return None

    return " ".join(words[: min(6, len(words))])


# ---------------------------------------------------------------------------
# Sentence / PDF text segmentation
# ---------------------------------------------------------------------------

def split_text_into_units(text):
    """
    Split PDF text into reasonably meaningful factual units.

    PDF extraction frequently produces:
      - line breaks in the middle of sentences
      - table rows
      - bullet points
      - multiple spaces

    We therefore normalize whitespace first and then split conservatively.
    """

    if not text:
        return []

    # Normalize unusual whitespace.
    text = text.replace("\u00a0", " ")
    text = text.replace("\u200b", "")
    text = text.replace("\r", "\n")

    # Collapse repeated spaces but preserve newlines temporarily.
    text = re.sub(r"[ \t]+", " ", text)

    # Remove obvious repeated separators.
    text = re.sub(r"[ \t]*([|])[\t ]*", r" \1 ", text)

    # Split first on strong sentence boundaries.
    chunks = re.split(
        r"(?<=[.!?])\s+"
        r"|(?<=;)\s+"
        r"|\n+",
        text,
    )

    results = []

    for chunk in chunks:
        chunk = re.sub(r"\s+", " ", chunk).strip()

        if not chunk:
            continue

        # Remove leading bullet symbols.
        chunk = re.sub(
            r"^[•●▪◦■□◆◇\-–—]+\s*",
            "",
            chunk,
        ).strip()

        if chunk:
            results.append(chunk)

    return results


# ---------------------------------------------------------------------------
# Numeric / measurement helpers
# ---------------------------------------------------------------------------

def contains_numeric_signal(sentence):
    """
    Decide whether a sentence contains a potentially meaningful measurement.
    """

    if NUMBER_RE.search(sentence):
        return True

    if CURRENCY_RE.search(sentence):
        # Currency alone is not enough, but this catches formats where the
        # number may have been separated by PDF extraction.
        return bool(re.search(r"\d", sentence))

    return False


def numeric_context(sentence):
    """
    Determine whether the numeric content looks like a real factual
    measurement rather than a page number or reference number.
    """

    if not contains_numeric_signal(sentence):
        return False

    # Remove common citation/reference patterns.
    cleaned = re.sub(
        r"\[\s*\d+(?:,\s*\d+)*\s*\]",
        "",
        sentence,
    )

    numbers = NUMBER_RE.findall(cleaned)

    if not numbers:
        return False

    # If there is a unit/currency or a factual verb, it is highly likely
    # to represent a useful fact.
    if UNIT_RE.search(cleaned):
        return True

    if CURRENCY_RE.search(cleaned):
        return True

    if DECLARATIVE.search(cleaned):
        return True

    # Standalone numbers are generally not useful facts.
    return False


# ---------------------------------------------------------------------------
# Confidence calculation
# ---------------------------------------------------------------------------

def calculate_numeric_confidence(
    sentence,
    dates,
    periods,
    ents,
    value,
    unit,
):
    confidence = 0.82
    warnings = []

    if value is not None:
        confidence += 0.04

    if unit:
        confidence += 0.04

    if ents:
        confidence += 0.04
    else:
        confidence -= 0.10
        warnings.append("no strong named entity detected")

    if dates:
        confidence += 0.03

    if periods:
        confidence += 0.02

    if not dates and not periods:
        warnings.append(
            "time scope was not explicitly extracted"
        )

    if not unit:
        warnings.append(
            "measurement unit may be implicit or unavailable"
        )

    return min(max(confidence, 0.10), 0.99), warnings


def calculate_semantic_confidence(
    sentence,
    dates,
    periods,
    ents,
):
    confidence = 0.58
    warnings = [
        "semantic fact without an extracted numeric value"
    ]

    if ents:
        confidence += 0.08
    else:
        confidence -= 0.12
        warnings.append(
            "entity resolution may be ambiguous"
        )

    if dates:
        confidence += 0.05

    if periods:
        confidence += 0.03

    if not dates and not periods:
        warnings.append(
            "time scope was not explicitly extracted"
        )

    return min(max(confidence, 0.10), 0.90), warnings


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_page_facts(text, page):
    """
    Extract facts from one PDF page.

    Important design principles:
      - No document-specific filenames or facts.
      - No hardcoded company names.
      - Numeric facts and semantic facts are both supported.
      - Every fact keeps the original sentence as evidence.
      - Normalization is delegated to normalizer.py.
      - Works with arbitrary PDFs rather than only the benchmark PDFs.
    """

    facts = []

    units = split_text_into_units(text)

    for raw in units:
        sentence = re.sub(r"\s+", " ", raw).strip()

        # Avoid extremely small fragments and massive PDF extraction blocks.
        if len(sentence) < 20:
            continue

        if len(sentence) > 1000:
            # Long PDF fragments are often table dumps or multiple unrelated
            # sentences. Split them once more.
            sub_units = re.split(
                r"(?<=[.!?])\s+|;\s+",
                sentence,
            )
        else:
            sub_units = [sentence]

        for current in sub_units:
            sentence = re.sub(r"\s+", " ", current).strip()

            if len(sentence) < 20 or len(sentence) > 1000:
                continue

            # Ignore obvious headers/footers that are just numbers.
            if not re.search(r"[A-Za-z]", sentence):
                continue

            dates = extract_dates(sentence) or []
            periods = extract_period_tokens(sentence) or []
            ents = entities(sentence)

            # ---------------------------------------------------------------
            # Numerical fact
            # ---------------------------------------------------------------

            if numeric_context(sentence):

                try:
                    value, unit, normalized_value, normalized_unit = (
                        extract_numeric(sentence)
                    )
                except Exception:
                    # Never let one malformed PDF sentence crash ingestion.
                    value = None
                    unit = None
                    normalized_value = None
                    normalized_unit = None

                if value is not None:

                    confidence, warnings = calculate_numeric_confidence(
                        sentence=sentence,
                        dates=dates,
                        periods=periods,
                        ents=ents,
                        value=value,
                        unit=unit,
                    )

                    facts.append(
                        CandidateFact(
                            text=sentence,
                            evidence=sentence,
                            fact_type="numerical",
                            subject=subject_guess(sentence),
                            predicate="contains_measurement",
                            value=value,
                            unit=unit,
                            normalized_value=normalized_value,
                            normalized_unit=normalized_unit,
                            dates=dates + periods,
                            entities=ents,
                            confidence=confidence,
                            warnings=warnings,
                        )
                    )

                    continue

            # ---------------------------------------------------------------
            # Semantic fact
            # ---------------------------------------------------------------

            if DECLARATIVE.search(sentence):

                confidence, warnings = calculate_semantic_confidence(
                    sentence=sentence,
                    dates=dates,
                    periods=periods,
                    ents=ents,
                )

                facts.append(
                    CandidateFact(
                        text=sentence,
                        evidence=sentence,
                        fact_type="semantic",
                        subject=subject_guess(sentence),
                        predicate="assertion",
                        value=None,
                        unit=None,
                        normalized_value=None,
                        normalized_unit=None,
                        dates=dates + periods,
                        entities=ents,
                        confidence=confidence,
                        warnings=warnings,
                    )
                )

    return facts
