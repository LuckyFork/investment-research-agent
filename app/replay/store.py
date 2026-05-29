import json
from pathlib import Path

from app.models.agent_task import TaskRunTrace
from app.replay.serializer import trace_from_dict, trace_to_dict


def save_trace(trace: TaskRunTrace, output_dir: str) -> str:
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    target = path / f"{trace.trace_id}.json"
    target.write_text(
        json.dumps(trace_to_dict(trace), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    trace.artifact_path = str(target)
    return str(target)


def load_trace(path: str) -> TaskRunTrace:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    trace = trace_from_dict(data)
    trace.artifact_path = path
    return trace
