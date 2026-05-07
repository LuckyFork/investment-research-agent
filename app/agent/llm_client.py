from typing import AsyncGenerator
from openai import AsyncOpenAI
from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.chat import ChatMessage

logger = get_logger(__name__)

SYSTEM_PROMPT = """你是一名专业的投研助手，服务于证券研究和投顾场景。
你的职责包括：研报问答、公告分析、财务数据解读、跨文档对比分析和合规预检。
回答时请：
1. 保持客观，引用数据时说明来源
2. 对不确定的信息明确标注"需要核实"
3. 涉及投资建议时提示用户自行判断风险"""

_client: AsyncOpenAI | None = None


def get_llm_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        settings = get_settings()
        kwargs: dict = {"api_key": settings.llm_api_key}
        if settings.llm_base_url:
            kwargs["base_url"] = settings.llm_base_url
        _client = AsyncOpenAI(**kwargs)
    return _client


def _to_oai_messages(messages: list[ChatMessage]) -> list[dict]:
    return [{"role": m.role, "content": m.content} for m in messages]


async def stream_chat(
    messages: list[ChatMessage],
    system: str = SYSTEM_PROMPT,
) -> AsyncGenerator[str, None]:
    settings = get_settings()
    oai_messages = [{"role": "system", "content": system}] + _to_oai_messages(messages)
    logger.info("llm_stream_start", model=settings.llm_model, turns=len(messages))

    stream = await get_llm_client().chat.completions.create(
        model=settings.llm_model,
        max_tokens=settings.llm_max_tokens,
        messages=oai_messages,
        stream=True,
    )
    async for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta

    logger.info("llm_stream_done")


async def complete_chat(
    messages: list[ChatMessage],
    system: str = SYSTEM_PROMPT,
) -> str:
    settings = get_settings()
    oai_messages = [{"role": "system", "content": system}] + _to_oai_messages(messages)
    logger.info("llm_complete_start", model=settings.llm_model, turns=len(messages))

    response = await get_llm_client().chat.completions.create(
        model=settings.llm_model,
        max_tokens=settings.llm_max_tokens,
        messages=oai_messages,
    )

    content = response.choices[0].message.content or ""
    usage = response.usage
    if usage:
        logger.info("llm_complete_done", input_tokens=usage.prompt_tokens,
                    output_tokens=usage.completion_tokens)
    return content
