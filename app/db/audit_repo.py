from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditEvent


async def create_audit_event(
    session: AsyncSession,
    *,
    trace_id: str,
    session_id: str,
    tenant_id: str,
    user_id: str,
    channel: str,
    event_type: str,
    model_version: str,
    prompt_version: str,
    rule_version: str,
    tool_name: str,
    tool_args: dict,
    tool_result_preview: str,
    policy_decision: dict,
    decision_payload: dict,
    intent_type: str,
    action_type: str,
    confidence: float | None,
    citations: list[dict],
    fallback_reason: str,
    compliance_passed: bool | None,
    compliance_issues: list[dict],
    message_preview: str,
    error_message: str,
) -> AuditEvent:
    event = AuditEvent(
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
        tool_args=tool_args,
        tool_result_preview=tool_result_preview,
        policy_decision=policy_decision,
        decision_payload=decision_payload,
        intent_type=intent_type,
        action_type=action_type,
        confidence=confidence,
        citations=citations,
        fallback_reason=fallback_reason,
        compliance_passed=compliance_passed,
        compliance_issues=compliance_issues,
        message_preview=message_preview,
        error_message=error_message,
    )
    session.add(event)
    await session.flush()
    return event
