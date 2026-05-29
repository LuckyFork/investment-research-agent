import re

from app.evals.models import EvalCase, EvalResult
from app.models.agent_task import TaskRunTrace
from app.models.decision import QueryAnalysis

_DOC_PATTERN = re.compile(r"文档:([^\s]+)")
_PAGE_PATTERN = re.compile(r"第(\d+)页")


def _trace_text(trace: TaskRunTrace | None) -> str:
    if trace is None:
        return ""
    parts = [trace.final_answer]
    for step in trace.step_results:
        preview = step.output_payload.get("result_preview", "")
        if preview:
            parts.append(str(preview))
    return "\n".join(parts)


def score_route(case: EvalCase, analysis: QueryAnalysis | None) -> bool | None:
    if case.expected_route is None or analysis is None:
        return None
    return analysis.route == case.expected_route


def score_document_hit(case: EvalCase, trace: TaskRunTrace | None) -> bool | None:
    if not case.expected_documents:
        return None
    haystack = _trace_text(trace)
    found_docs = set(_DOC_PATTERN.findall(haystack))
    return any(doc_id in found_docs for doc_id in case.expected_documents)


def score_page_hit(case: EvalCase, trace: TaskRunTrace | None) -> bool | None:
    if not case.expected_pages:
        return None
    haystack = _trace_text(trace)
    found_pages = {int(page) for page in _PAGE_PATTERN.findall(haystack)}
    return any(page in found_pages for page in case.expected_pages)


def score_keyword_hit(case: EvalCase, answer: str) -> float:
    if not case.must_include_terms:
        return 1.0
    if not answer:
        return 0.0
    hits = sum(1 for term in case.must_include_terms if term in answer)
    return hits / len(case.must_include_terms)


def score_compliance(case: EvalCase, compliance_passed: bool | None) -> bool | None:
    if case.should_pass_compliance is None or compliance_passed is None:
        return None
    return compliance_passed == case.should_pass_compliance


def score_case(
    *,
    case: EvalCase,
    analysis: QueryAnalysis | None,
    answer: str,
    compliance_passed: bool | None,
    trace: TaskRunTrace | None = None,
    trace_path: str = "",
) -> EvalResult:
    result = EvalResult(
        case_id=case.id,
        query=case.query,
        actual_complexity=analysis.complexity if analysis else None,
        actual_route=analysis.route if analysis else None,
        route_correct=score_route(case, analysis),
        document_hit=score_document_hit(case, trace),
        page_hit=score_page_hit(case, trace),
        keyword_hit_ratio=score_keyword_hit(case, answer),
        compliance_correct=score_compliance(case, compliance_passed),
        compliance_passed=compliance_passed,
        trace_path=trace_path,
        answer_preview=answer[:300],
    )
    if trace is None and case.expected_documents:
        result.notes.append("no_trace_for_document_scoring")
    return result
