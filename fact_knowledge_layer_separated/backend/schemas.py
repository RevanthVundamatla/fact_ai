from pydantic import BaseModel
from typing import Optional, List, Any

class UploadResponse(BaseModel):
    documents: List[dict]

class AnalyzeResponse(BaseModel):
    documents_processed: int
    facts_created: int
    relationships_created: int

class FactOut(BaseModel):
    id: int
    document_id: int
    page: int
    text: str
    evidence: str
    fact_type: str
    subject: Optional[str]
    predicate: Optional[str]
    value: Optional[float]
    unit: Optional[str]
    normalized_value: Optional[float]
    normalized_unit: Optional[str]
    dates: List[str]
    entities: List[str]
    confidence: float
    warnings: List[str]

class RelationshipOut(BaseModel):
    id: int
    fact_a: int
    fact_b: int
    relation: str
    score: float
    explanation: str
    signals: Any
