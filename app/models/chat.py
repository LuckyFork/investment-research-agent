import time
from typing import Literal
from pydantic import BaseModel, Field, field_validator


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    created_at: float = Field(default_factory=time.time)


class ChatRequest(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=128)
    message: str = Field(..., min_length=1, max_length=10000)
    stream: bool = True

    @field_validator("message")
    @classmethod
    def message_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("message must not be blank")
        return v


class ChatStreamEvent(BaseModel):
    type: Literal["text", "done", "error", "tool_start", "tool_done", "compliance"]
    content: str = ""
    session_id: str = ""
    tool_name: str = ""              # tool_start / tool_done
    compliance_passed: bool = True   # compliance event only
    compliance_issues: list[dict] = []  # list of ComplianceIssue dicts


class SessionHistoryResponse(BaseModel):
    session_id: str
    messages: list[ChatMessage]
    total: int
