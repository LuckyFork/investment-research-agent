from dataclasses import dataclass
from uuid import uuid4

from fastapi import Header, HTTPException, status


@dataclass(frozen=True)
class RequestContext:
    user_id: str
    tenant_id: str
    request_id: str = ""
    channel: str = "api"


def build_scoped_session_id(context: RequestContext, session_id: str) -> str:
    """Namespace a user session so two users cannot collide on the same session_id."""
    return f"{context.tenant_id}:{context.user_id}:{session_id}"


async def get_request_context(
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    x_request_id: str | None = Header(default=None, alias="X-Request-Id"),
    x_channel: str | None = Header(default=None, alias="X-Channel"),
) -> RequestContext:
    """
    Lightweight request identity for the current MVP.

    The project does not yet integrate a real auth provider, so we explicitly
    require caller-provided headers for every protected endpoint. This gives us
    a stable context for isolation and auditing work without overbuilding auth.
    """
    if not x_user_id or not x_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing request identity headers: X-User-Id and X-Tenant-Id are required",
        )

    return RequestContext(
        user_id=x_user_id.strip(),
        tenant_id=x_tenant_id.strip(),
        request_id=(x_request_id or str(uuid4())).strip(),
        channel=(x_channel or "api").strip() or "api",
    )
