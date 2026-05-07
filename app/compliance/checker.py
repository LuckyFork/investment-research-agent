"""
Rule-based compliance checker.
Runs synchronously (regex only, no I/O) so it never blocks the event loop.
"""

import re
from app.compliance.models import ComplianceIssue, ComplianceResult
from app.compliance.rules import RULES
from app.core.logging import get_logger

logger = get_logger(__name__)

_SNIPPET_PRE = 15   # chars before match start
_SNIPPET_POST = 40  # chars after match end


def _snippet(text: str, m: re.Match) -> str:
    start = max(0, m.start() - _SNIPPET_PRE)
    end = min(len(text), m.end() + _SNIPPET_POST)
    raw = text[start:end].strip()
    # Prefix ellipsis if we truncated the left side
    return ("…" if start > 0 else "") + raw + ("…" if end < len(text) else "")


def check_compliance(text: str) -> ComplianceResult:
    """
    Scan `text` against every rule in RULES.

    - `passed` is True unless at least one error-level issue is found.
    - Warning-level issues are recorded but do not set passed=False,
      giving the frontend the option to annotate without blocking.
    """
    if not text.strip():
        return ComplianceResult(passed=True, issues=[])

    issues: list[ComplianceIssue] = []

    for rule in RULES:
        compiled = re.compile(rule.pattern, re.IGNORECASE)
        for m in compiled.finditer(text):
            issues.append(
                ComplianceIssue(
                    level=rule.level,
                    rule=rule.rule,
                    description=rule.description,
                    snippet=_snippet(text, m),
                )
            )

    passed = not any(i.level == "error" for i in issues)
    logger.info("compliance_checked", text_len=len(text),
                issues=len(issues), passed=passed)
    return ComplianceResult(passed=passed, issues=issues)
