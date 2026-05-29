from app.models.agent_task import TaskRunTrace


def trace_to_dict(trace: TaskRunTrace) -> dict:
    return trace.model_dump(mode="json")


def trace_from_dict(data: dict) -> TaskRunTrace:
    return TaskRunTrace.model_validate(data)
