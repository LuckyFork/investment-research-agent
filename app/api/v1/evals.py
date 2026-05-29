from pathlib import Path
import json

from fastapi import APIRouter

from app.core.config import get_settings
from app.models.common import BaseResponse

router = APIRouter(prefix="/evals", tags=["evals"])


def _load_eval_artifact(filename: str) -> dict | list:
    settings = get_settings()
    path = Path(settings.eval_output_dir) / filename
    if not path.exists():
        return {} if filename.endswith("summary.json") else []
    return json.loads(path.read_text(encoding="utf-8"))


@router.get("/latest-summary", response_model=BaseResponse[dict])
async def get_latest_eval_summary():
    return BaseResponse(data=_load_eval_artifact("latest-summary.json"))


@router.get("/latest-details", response_model=BaseResponse[list])
async def get_latest_eval_details():
    return BaseResponse(data=_load_eval_artifact("latest-details.json"))
