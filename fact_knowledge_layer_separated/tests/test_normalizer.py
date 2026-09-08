from backend.normalizer import normalize_value, parse_number

def test_currency_million():
    v, u = normalize_value(12.4, "million usd")
    assert v == 12_400_000
    assert u == "currency_usd"

def test_kg_tonne():
    v, u = normalize_value(2, "tonnes")
    assert v == 2000
    assert u == "kg"

def test_suffix_number():
    assert parse_number("2.5m") == 2_500_000
