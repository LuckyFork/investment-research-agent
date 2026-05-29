from pydantic import BaseModel, Field

from app.models.decision import QueryComplexity, RetrievalRoute


class EvalCase(BaseModel):
    id: str
    query: str
    expected_complexity: QueryComplexity | None = None
    expected_route: RetrievalRoute | None = None
    expected_documents: list[str] = Field(default_factory=list)
    expected_pages: list[int] = Field(default_factory=list)
    must_include_terms: list[str] = Field(default_factory=list)
    should_pass_compliance: bool | None = None


class EvalResult(BaseModel):
    case_id: str
    query: str
    actual_complexity: QueryComplexity | None = None
    actual_route: RetrievalRoute | None = None
    route_correct: bool | None = None
    document_hit: bool | None = None
    page_hit: bool | None = None
    keyword_hit_ratio: float = 0.0
    compliance_correct: bool | None = None
    compliance_passed: bool | None = None
    trace_path: str = ""
    answer_preview: str = ""
    notes: list[str] = Field(default_factory=list)


class EvalSummary(BaseModel):
    total_cases: int
    route_accuracy: float = 0.0
    document_hit_rate: float = 0.0
    page_hit_rate: float = 0.0
    keyword_hit_rate: float = 0.0
    compliance_accuracy: float = 0.0
