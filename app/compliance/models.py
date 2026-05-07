from typing import Literal
from pydantic import BaseModel


class ComplianceIssue(BaseModel):
    level: Literal["warning", "error"]
    rule: str       # rule code, e.g. "PRO_001"
    description: str
    snippet: str    # surrounding text excerpt that triggered the rule


class ComplianceResult(BaseModel):
    passed: bool                    # False only when at least one error-level issue found
    issues: list[ComplianceIssue]
