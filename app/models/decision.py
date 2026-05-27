from enum import Enum

from pydantic import BaseModel, Field


class IntentType(str, Enum):
    FACT_LOOKUP = "fact_lookup"
    DOCUMENT_SUMMARY = "document_summary"
    RESEARCH_ANALYSIS = "research_analysis"
    INVESTMENT_OPINION = "investment_opinion"
    PERSONALIZED_ADVICE_REQUEST = "personalized_advice_request"
    HIGH_RISK_REQUEST = "high_risk_request"
    UNKNOWN = "unknown"


class ActionType(str, Enum):
    ANSWER_DIRECTLY = "answer_directly"
    SEARCH_DOCUMENTS = "search_documents"
    SUMMARIZE_WITH_CITATIONS = "summarize_with_citations"
    ASK_CLARIFYING_QUESTION = "ask_clarifying_question"
    SAFE_REFUSAL = "safe_refusal"
    HANDOFF_TO_HUMAN = "handoff_to_human"


class IntentAssessment(BaseModel):
    intent_type: IntentType
    user_goal: str
    reasoning: str
    confidence: float = Field(ge=0.0, le=1.0)


class ActionProposal(BaseModel):
    action_type: ActionType
    requires_tool: bool = False
    tool_name: str = ""
    tool_args: dict = Field(default_factory=dict)
    fallback_action: ActionType = ActionType.SAFE_REFUSAL
    fallback_reason: str = ""


class Citation(BaseModel):
    document_id: str
    page_num: int | None = None
    section_title: str = ""
    snippet: str = ""


class EvidenceBundle(BaseModel):
    citations: list[Citation] = Field(default_factory=list)
    has_sufficient_evidence: bool = False
    evidence_gap: str = ""


class ResponseDraft(BaseModel):
    answer_draft: str
    includes_risk_note: bool = False
    is_personalized: bool = False
    needs_human_review: bool = False


class AgentDecision(BaseModel):
    intent: IntentAssessment
    action: ActionProposal
    evidence: EvidenceBundle
    response: ResponseDraft
