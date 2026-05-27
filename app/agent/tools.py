import json
from app.agent.retriever import search_documents as _search_docs
from app.core.logging import get_logger
from app.core.request_context import RequestContext

logger = get_logger(__name__)

# OpenAI-format tool schema passed to the LLM on every request
TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "search_documents",
            "description": (
                "在已上传的研究报告、财报、公告等文档中搜索与问题最相关的内容片段。"
                "当问题涉及具体数据、特定公司信息或需要引用文档内容时，请使用此工具。"
                "如果没有上传文档或问题属于通用知识，可直接回答，无需调用此工具。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "用自然语言描述要查找的内容，尽量具体（如公司名、指标名、时间范围等）",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "返回结果数量，默认 5，最多 10",
                        "default": 5,
                        "minimum": 1,
                        "maximum": 10,
                    },
                },
                "required": ["query"],
            },
        },
    }
]


def _format_search_results(results: list[dict]) -> str:
    if not results:
        return "未在已上传文档中找到相关内容。"

    parts: list[str] = []
    for i, r in enumerate(results, 1):
        section = f"【{r['section_title']}】" if r["section_title"] else ""
        header = f"[{i}] 文档:{r['document_id']}  第{r['page_num']}页{section}  相关度:{r['score']}"
        parts.append(f"{header}\n{r['text']}")

    return "\n\n---\n\n".join(parts)


async def execute_tool(name: str, args: dict, context: RequestContext) -> str:
    """Dispatch a tool call by name and return formatted string result."""
    logger.info("tool_execute", name=name, args=str(args)[:200])

    if name == "search_documents":
        top_k = max(1, min(int(args.get("top_k", 5)), 10))
        results = await _search_docs(
            query=args["query"],
            context=context,
            top_k=top_k,
        )
        return _format_search_results(results)

    raise ValueError(f"Unknown tool: {name}")
