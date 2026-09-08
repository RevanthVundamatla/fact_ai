import re
from dateutil import parser as dateparser

UNIT_FACTORS = {
    "kg": ("kg", 1.0), "kilogram": ("kg", 1.0), "kilograms": ("kg", 1.0),
    "g": ("kg", 0.001), "gram": ("kg", 0.001), "grams": ("kg", 0.001),
    "tonne": ("kg", 1000.0), "tonnes": ("kg", 1000.0), "t": ("kg", 1000.0),
    "lb": ("kg", 0.45359237), "lbs": ("kg", 0.45359237),
    "m": ("m", 1.0), "meter": ("m", 1.0), "meters": ("m", 1.0),
    "km": ("m", 1000.0), "kilometer": ("m", 1000.0), "kilometers": ("m", 1000.0),
    "cm": ("m", 0.01), "mm": ("m", 0.001),
    "usd": ("currency_usd", 1.0), "$": ("currency_usd", 1.0),
    "million usd": ("currency_usd", 1_000_000.0),
    "cr": ("currency_inr", 10_000_000.0), "crore": ("currency_inr", 10_000_000.0),
    "crores": ("currency_inr", 10_000_000.0), "₹ cr": ("currency_inr", 10_000_000.0),
    "₹ crore": ("currency_inr", 10_000_000.0), "₹ crores": ("currency_inr", 10_000_000.0),
    "m usd": ("currency_usd", 1_000_000.0),
    "billion usd": ("currency_usd", 1_000_000_000.0),
    "bn usd": ("currency_usd", 1_000_000_000.0),
    "percent": ("percent", 1.0), "%": ("percent", 1.0),
    "employees": ("people", 1.0), "employee": ("people", 1.0),
    "people": ("people", 1.0),
}

def parse_number(raw: str):
    s = raw.replace(",", "").strip().lower()
    mult = 1.0
    if s.endswith("k"):
        mult, s = 1_000.0, s[:-1]
    elif s.endswith("m"):
        mult, s = 1_000_000.0, s[:-1]
    elif s.endswith("b"):
        mult, s = 1_000_000_000.0, s[:-1]
    try:
        return float(s) * mult
    except ValueError:
        return None

def normalize_value(value, unit):
    if value is None or not unit:
        return value, unit
    key = unit.lower().strip()
    if key in UNIT_FACTORS:
        normalized_unit, factor = UNIT_FACTORS[key]
        return value * factor, normalized_unit
    return value, key

def extract_dates(text: str):
    out = []
    for m in re.finditer(r"\b(?:19|20)\d{2}\b", text):
        out.append(m.group(0))
    for m in re.finditer(r"\bQ[1-4]\s*(?:FY)?\s*(?:19|20)?\d{2}\b", text, re.I):
        out.append(m.group(0))
    return list(dict.fromkeys(out))

def extract_period_tokens(text: str):
    lower = text.lower()
    periods = []
    if "quarter" in lower or re.search(r"\bq[1-4]\b", lower):
        periods.append("quarter")
    if "annual" in lower or "year ended" in lower or "fiscal year" in lower or "fy" in lower:
        periods.append("year")
    if "month" in lower:
        periods.append("month")
    if "day" in lower or "daily" in lower:
        periods.append("day")
    return periods

def extract_numeric(text: str):
    # Handles $12.4m, 12.4 million USD, 2,000 kg, 45%, etc.
    patterns = [
        r"₹\\s*([\\d,.]+)\\s*(crore|crores|cr)\\b",
        r"\\b([\\d,.]+)\\s*(crore|crores|cr)\\b",

        r"\$\s*([\d,.]+)\s*(million|billion|m|bn|b)?",
        r"\b([\d,.]+)\s*(million|billion|m|bn|b)\s*(usd|dollars?)?\b",
        r"\b([\d,.]+)\s*(kg|kilograms?|g|grams?|tonnes?|tonne|t|km|kilometers?|m|meters?|cm|mm|%|percent|employees?|people)\b",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if not m:
            continue
        groups = m.groups()
        raw_num = groups[0]
        value = parse_number(raw_num)
        unit = "$"
        if len(groups) > 1 and groups[1]:
            qualifier = groups[1].lower()
            unit = qualifier if qualifier not in {"b", "bn"} else ("billion usd" if qualifier in {"b","bn"} else qualifier)
            if "$" in text[:m.start()+1]:
                unit = f"{qualifier} usd"
        if len(groups) > 2 and groups[2]:
            unit = groups[2]
        if "%" in text[m.start():m.end()] or re.search(r"percent", text[m.start():m.end()], re.I):
            unit = "%"
        if value is not None:
            nv, nu = normalize_value(value, unit)
            return value, unit, nv, nu
    return None, None, None, None
