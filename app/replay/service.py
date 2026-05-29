from pathlib import Path

from app.models.agent_task import TaskRunTrace
from app.replay.store import load_trace
from app.replay.summary import summarize_trace


def list_trace_summaries(output_dir: str, limit: int = 20) -> list[dict]:
    base = Path(output_dir)
    if not base.exists():
        return []

    paths = sorted(
        base.glob("*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    summaries: list[dict] = []
    for path in paths[:limit]:
        trace = load_trace(str(path))
        summary = summarize_trace(trace)
        summary["updated_at"] = path.stat().st_mtime
        summaries.append(summary)
    return summaries


def get_trace(trace_id: str, output_dir: str) -> TaskRunTrace:
    return load_trace(str(Path(output_dir) / f"{trace_id}.json"))


def get_trace_summary(trace_id: str, output_dir: str) -> dict:
    trace = get_trace(trace_id, output_dir)
    return summarize_trace(trace)


def get_latest_trace_for_session(session_id: str, output_dir: str) -> dict | None:
    for summary in list_trace_summaries(output_dir, limit=200):
        if summary["session_id"] == session_id:
            return summary
    return None
