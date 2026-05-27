from app.core.db import get_session_factory
from app.core.logging import get_logger
from app.db import audit_repo

logger = get_logger(__name__)


def _clip_text(text: str, limit: int = 2000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit]


async def record_audit_event(
    *,
    trace_id: str,
    session_id: str,
    tenant_id: str,
    user_id: str,
    channel: str,
    event_type: str,
    model_version: str = "",
    prompt_version: str = "",
    rule_version: str = "",
    tool_name: str = "",
    tool_args: dict | None = None,
    tool_result_preview: str = "",
    policy_decision: dict | None = None,
    decision_payload: dict | None = None,
    intent_type: str = "",
    action_type: str = "",
    confidence: float | None = None,
    citations: list[dict] | None = None,
    fallback_reason: str = "",
    compliance_passed: bool | None = None,
    compliance_issues: list[dict] | None = None,
    message_preview: str = "",
    error_message: str = "",
) -> None:
    """
    Best-effort audit persistence.

    The agent must keep serving even if audit persistence is temporarily down,
    so failures are logged but not raised to callers.
    """
    try:
        session_factory = get_session_factory()
        async with session_factory() as session:
            async with session.begin():
                await audit_repo.create_audit_event(
                    session,
                    trace_id=trace_id,
                    session_id=session_id,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    channel=channel,
                    event_type=event_type,
                    model_version=model_version,
                    prompt_version=prompt_version,
                    rule_version=rule_version,
                    tool_name=tool_name,
                    tool_args=tool_args or {},
                    tool_result_preview=_clip_text(tool_result_preview),
                    policy_decision=policy_decision or {},
                    decision_payload=decision_payload or {},
                    intent_type=intent_type,
                    action_type=action_type,
                    confidence=confidence,
                    citations=citations or [],
                    fallback_reason=_clip_text(fallback_reason),
                    compliance_passed=compliance_passed,
                    compliance_issues=compliance_issues or [],
                    message_preview=_clip_text(message_preview),
                    error_message=_clip_text(error_message, limit=1000),
                )
    except Exception as exc:
        logger.error(
            "audit_record_failed",
            trace_id=trace_id,
            event_type=event_type,
            error=str(exc),
        )
