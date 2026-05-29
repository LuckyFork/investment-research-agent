import argparse
import asyncio
import json
from pathlib import Path

from app.core.config import get_settings
from app.core.request_context import RequestContext
from app.evals.runner import load_eval_cases, run_eval_suite


def _context_factory(case, idx: int) -> RequestContext:
    return RequestContext(
        user_id="eval-user",
        tenant_id="eval-tenant",
        request_id=f"eval-{idx:03d}-{case.id}",
        channel="eval",
    )


async def _main(cases_path: str, output_dir: str) -> None:
    settings = get_settings()
    cases = load_eval_cases(cases_path)
    results, summary = await run_eval_suite(cases, context_factory=_context_factory)

    output = Path(output_dir or settings.eval_output_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / "latest-summary.json").write_text(
        json.dumps(summary.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output / "latest-details.json").write_text(
        json.dumps([item.model_dump(mode="json") for item in results], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run replay/eval benchmark cases.")
    parser.add_argument("--cases", default="evals/cases.json")
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    asyncio.run(_main(args.cases, args.output))
