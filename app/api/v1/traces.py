from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.config import get_settings
from app.core.request_context import RequestContext, build_scoped_session_id, get_request_context
from app.models.common import BaseResponse
from app.replay.service import (
    get_latest_trace_for_session,
    get_trace,
    get_trace_summary,
    list_trace_summaries,
)

router = APIRouter(prefix="/traces", tags=["traces"])


@router.get("", response_model=BaseResponse[list[dict]])
async def list_traces(
    limit: int = Query(20, ge=1, le=100),
    context: RequestContext = Depends(get_request_context),
):
    settings = get_settings()
    traces = [
        item
        for item in list_trace_summaries(settings.trace_output_dir, limit=limit)
        if item["session_id"].startswith(f"{context.tenant_id}:{context.user_id}:")
    ]
    return BaseResponse(data=traces)


@router.get("/{trace_id}", response_model=BaseResponse[dict])
async def get_trace_detail(
    trace_id: str,
    context: RequestContext = Depends(get_request_context),
):
    settings = get_settings()
    path = Path(settings.trace_output_dir) / f"{trace_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Trace not found")

    trace = get_trace(trace_id, settings.trace_output_dir)
    expected_prefix = f"{context.tenant_id}:{context.user_id}:"
    if not trace.session_id.startswith(expected_prefix):
        raise HTTPException(status_code=404, detail="Trace not found")
    return BaseResponse(data=trace.model_dump(mode="json"))


@router.get("/{trace_id}/summary", response_model=BaseResponse[dict])
async def get_trace_detail_summary(
    trace_id: str,
    context: RequestContext = Depends(get_request_context),
):
    settings = get_settings()
    path = Path(settings.trace_output_dir) / f"{trace_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Trace not found")
    trace = get_trace(trace_id, settings.trace_output_dir)
    expected_prefix = f"{context.tenant_id}:{context.user_id}:"
    if not trace.session_id.startswith(expected_prefix):
        raise HTTPException(status_code=404, detail="Trace not found")
    return BaseResponse(data=get_trace_summary(trace_id, settings.trace_output_dir))


@router.get("/sessions/{session_id}/latest", response_model=BaseResponse[dict | None])
async def get_latest_trace(
    session_id: str,
    context: RequestContext = Depends(get_request_context),
):
    settings = get_settings()
    scoped_session_id = build_scoped_session_id(context, session_id)
    trace = get_latest_trace_for_session(scoped_session_id, settings.trace_output_dir)
    return BaseResponse(data=trace)
