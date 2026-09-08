import json
from backend.relation_engine import relationship

def fact(text, value, unit, entity="Acme", dates=None, nv=None, nu=None):
    return {
        "text": text,
        "entities": json.dumps([entity]),
        "normalized_value": nv if nv is not None else value,
        "normalized_unit": nu or unit,
        "dates": json.dumps(dates or ["2025"])
    }

def test_corroborates():
    a=fact("Acme revenue was $12.4 million in FY2025.", 12400000, "currency_usd", nv=12400000)
    b=fact("FY2025 sales reached 12.4M USD.", 12400000, "currency_usd", nv=12400000)
    rel,score,_,_=relationship(a,b)
    assert rel == "CORROBORATES"

def test_contradicts():
    a=fact("Acme has 420 employees in 2025.", 420, "people")
    b=fact("Acme has 610 employees in 2025.", 610, "people")
    rel,score,_,_=relationship(a,b)
    assert rel == "CONTRADICTS"

def test_reconciles_different_period():
    a=fact("Acme revenue was $8 million in Q1 2025.", 8000000, "currency_usd", dates=["2025","quarter"])
    b=fact("Acme revenue was $32 million for FY2025.", 32000000, "currency_usd", dates=["2025","year"])
    rel,score,_,_=relationship(a,b)
    assert rel == "RECONCILES"
