from backend.fact_extractor import extract_page_facts

def test_numeric_fact():
    facts = extract_page_facts("Acme reported revenue of $12.4 million in FY2025.", 1)
    assert facts
    assert facts[0].normalized_value == 12_400_000

def test_semantic_fact():
    facts = extract_page_facts("Acme operates three manufacturing sites in Chennai.", 1)
    assert facts
    assert facts[0].fact_type == "semantic"
