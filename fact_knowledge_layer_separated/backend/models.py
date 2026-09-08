from dataclasses import dataclass, field
from typing import Optional, List

@dataclass
class CandidateFact:
    text: str
    evidence: str
    fact_type: str
    subject: Optional[str] = None
    predicate: Optional[str] = None
    value: Optional[float] = None
    unit: Optional[str] = None
    normalized_value: Optional[float] = None
    normalized_unit: Optional[str] = None
    dates: List[str] = field(default_factory=list)
    entities: List[str] = field(default_factory=list)
    confidence: float = 0.5
    warnings: List[str] = field(default_factory=list)
