from pydantic import BaseModel, Field

from app.models.decision import ActionType


class PolicyDecision(BaseModel):
    allowed: bool
    reason_code: str
    reason: str
    user_message: str
    sanitized_args: dict = Field(default_factory=dict)


class ScenePolicyResult(BaseModel):
    allowed: bool
    reason_code: str
    reason: str
    user_message: str = ""
    final_action: ActionType
    allow_tool: bool = False
    requires_citations: bool = False
    requires_human_review: bool = False
