import json
from pathlib import Path

from app.agent.agent_loop import COMPLIANCE_BLOCK_MESSAGE, run_agent
from app.agent.query_classifier import classify_query, refine_query_analysis
from app.core.config import get_settings
from app.core.request_context import RequestContext
from app.evals.models import EvalCase, EvalResult, EvalSummary
from app.evals.scorer import score_case
from app.replay import load_trace


def load_eval_cases(path: str) -> list[EvalCase]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [EvalCase.model_validate(item) for item in data]


async def run_eval_case(case: EvalCase, *, session_id: str, context: RequestContext) -> EvalResult:
    settings = get_settings()
    rule_analysis = classify_query(case.query)
    refined_analysis = await refine_query_analysis(case.query, rule_analysis)

    events = [event async for event in run_agent(session_id, case.query, context)]
    answer_text = "".join(event.content for event in events if event.type == "text")
    if answer_text == COMPLIANCE_BLOCK_MESSAGE:
        compliance_passed = False
    else:
        compliance_events = [event for event in events if event.type == "compliance"]
        compliance_passed = compliance_events[-1].compliance_passed if compliance_events else None

    trace_path = str(Path(settings.trace_output_dir) / f"{context.request_id}.json")
    trace = load_trace(trace_path) if Path(trace_path).exists() else None
    return score_case(
        case=case,
        analysis=refined_analysis,
        answer=answer_text,
        compliance_passed=compliance_passed,
        trace=trace,
        trace_path=trace_path if trace is not None else "",
    )


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


async def run_eval_suite(cases: list[EvalCase], *, context_factory) -> tuple[list[EvalResult], EvalSummary]:
    results: list[EvalResult] = []
    for idx, case in enumerate(cases, start=1):
        context = context_factory(case, idx)
        result = await run_eval_case(case, session_id=f"eval-{case.id}", context=context)
        results.append(result)

    summary = EvalSummary(
        total_cases=len(results),
        route_accuracy=_mean([1.0 for item in results if item.route_correct is True] + [0.0 for item in results if item.route_correct is False]),
        document_hit_rate=_mean([1.0 for item in results if item.document_hit is True] + [0.0 for item in results if item.document_hit is False]),
        page_hit_rate=_mean([1.0 for item in results if item.page_hit is True] + [0.0 for item in results if item.page_hit is False]),
        keyword_hit_rate=_mean([item.keyword_hit_ratio for item in results]),
        compliance_accuracy=_mean([1.0 for item in results if item.compliance_correct is True] + [0.0 for item in results if item.compliance_correct is False]),
    )
    return results, summary
