import json

from app.agent.llm_client import PROMPT_VERSION, SYSTEM_PROMPT, get_llm_client
from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.chat import ChatMessage
from app.models.decision import AgentDecision

logger = get_logger(__name__)

DECISION_PROMPT_VERSION = f"{PROMPT_VERSION}-decision-v1"

_DECISION_SYSTEM = f"""{SYSTEM_PROMPT}

你现在不是直接回答用户，而是先输出一个严格 JSON 决策对象。
目标是帮助后端系统判断：用户意图是什么、是否需要调用工具、是否应该拒绝或转人工。

必须遵守：
1. 只输出 JSON，不要加 markdown 代码块
2. 字段必须完整
3. 如果用户在索要投资建议、个性化推荐、高收益高风险选择，请将 intent_type 归类到
   investment_opinion / personalized_advice_request / high_risk_request 之一
4. 如果是事实查询、文档总结、研究分析，可分别归类为 fact_lookup / document_summary / research_analysis
5. 如果判断证据不足，has_sufficient_evidence 必须为 false，并给出 evidence_gap
6. 如果需要检索文档，action_type 应为 search_documents 或 summarize_with_citations，并填好 tool_name/tool_args
7. 如果不应该直接回答，请使用 ask_clarifying_question / safe_refusal / handoff_to_human

JSON schema:
{{
  "intent": {{
    "intent_type": "fact_lookup|document_summary|research_analysis|investment_opinion|personalized_advice_request|high_risk_request|unknown",
    "user_goal": "string",
    "reasoning": "string",
    "confidence": 0.0
  }},
  "action": {{
    "action_type": "answer_directly|search_documents|summarize_with_citations|ask_clarifying_question|safe_refusal|handoff_to_human",
    "requires_tool": false,
    "tool_name": "",
    "tool_args": {{}},
    "fallback_action": "safe_refusal",
    "fallback_reason": ""
  }},
  "evidence": {{
    "citations": [],
    "has_sufficient_evidence": false,
    "evidence_gap": ""
  }},
  "response": {{
    "answer_draft": "string",
    "includes_risk_note": false,
    "is_personalized": false,
    "needs_human_review": false
  }}
}}"""

_FINAL_ANSWER_SYSTEM = f"""{SYSTEM_PROMPT}

请基于结构化决策对象和工具返回结果生成最终中文答复。
要求：
1. 仅依据提供的工具结果，不要编造未检索到的事实
2. 回答尽量引用工具结果中的文档编号/页码线索
3. 不要承诺收益，不要生成个性化投资建议
4. 如果工具结果表明证据不足，要明确说明需要进一步核实
5. 直接输出最终答复正文"""


def _extract_json_payload(content: str) -> str:
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("No JSON object found in decision response")
    return text[start:end + 1]


def _history_to_messages(history: list[ChatMessage], summary: str = "") -> list[dict]:
    system = _DECISION_SYSTEM
    if summary:
        system = f"{system}\n\n[历史对话背景]\n{summary}"
    return [{"role": "system", "content": system}] + [
        {"role": msg.role, "content": msg.content} for msg in history
    ]


async def plan_next_step(history: list[ChatMessage], summary: str = "") -> AgentDecision:
    settings = get_settings()
    response = await get_llm_client().chat.completions.create(
        model=settings.llm_model,
        max_tokens=1200,
        messages=_history_to_messages(history, summary),
    )
    content = response.choices[0].message.content or ""
    payload = _extract_json_payload(content)
    logger.info("decision_generated", prompt_version=DECISION_PROMPT_VERSION)
    return AgentDecision.model_validate(json.loads(payload))


async def generate_answer_from_tool(
    decision: AgentDecision,
    user_message: str,
    tool_result: str,
    summary: str = "",
) -> str:
    settings = get_settings()
    context_parts: list[str] = []
    if summary:
        context_parts.append(f"[历史对话背景]\n{summary}")
    context_parts.append(f"[用户问题]\n{user_message}")
    context_parts.append(
        "[结构化决策]\n" + json.dumps(decision.model_dump(), ensure_ascii=False, indent=2)
    )
    context_parts.append(f"[工具返回]\n{tool_result}")
    prompt = "\n\n".join(context_parts)

    response = await get_llm_client().chat.completions.create(
        model=settings.llm_model,
        max_tokens=settings.llm_max_tokens,
        messages=[
            {"role": "system", "content": _FINAL_ANSWER_SYSTEM},
            {"role": "user", "content": prompt},
        ],
    )
    return (response.choices[0].message.content or "").strip()
