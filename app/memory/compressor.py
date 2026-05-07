"""Compress older conversation turns into a compact summary via LLM."""

import json
from app.agent.llm_client import get_llm_client
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_COMPRESSOR_SYSTEM = (
    "你是对话历史压缩助手。"
    "请将用户提供的投研对话历史提炼为一段简洁摘要（200字以内）。"
    "重点保留：分析目标（公司/行业）、关键数据与结论、用户明确的偏好或约束。"
    "忽略：重复内容、寒暄客套。"
    "直接输出摘要正文，不要加任何前缀标签。"
)


def _format_messages(raw_messages: list[bytes | str]) -> str:
    lines: list[str] = []
    for raw in raw_messages:
        try:
            text = raw.decode() if isinstance(raw, bytes) else raw
            data = json.loads(text)
            role = "用户" if data.get("role") == "user" else "助手"
            content = data.get("content", "").strip()
            if content:
                lines.append(f"{role}：{content}")
        except (json.JSONDecodeError, AttributeError):
            continue
    return "\n".join(lines)


async def compress_old_messages(
    existing_summary: str,
    raw_messages: list[bytes | str],
) -> str:
    """
    Merge `existing_summary` with `raw_messages` and produce a new summary.
    Returns the summary string (empty string on LLM failure).
    """
    conversation_text = _format_messages(raw_messages)
    if not conversation_text and not existing_summary:
        return ""

    parts: list[str] = []
    if existing_summary:
        parts.append(f"[已有摘要]\n{existing_summary}")
    if conversation_text:
        parts.append(f"[待压缩的对话]\n{conversation_text}")
    parts.append("请将以上内容合并压缩为一段投研上下文摘要。")

    user_content = "\n\n".join(parts)
    settings = get_settings()

    logger.info("compress_start", existing_len=len(existing_summary),
                messages_count=len(raw_messages))

    response = await get_llm_client().chat.completions.create(
        model=settings.llm_model,
        max_tokens=512,
        messages=[
            {"role": "system", "content": _COMPRESSOR_SYSTEM},
            {"role": "user", "content": user_content},
        ],
    )

    summary = (response.choices[0].message.content or "").strip()
    logger.info("compress_done", summary_len=len(summary))
    return summary
