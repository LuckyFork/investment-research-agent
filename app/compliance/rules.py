"""
Compliance rule definitions for investment research content.
Each rule maps a regex pattern to a severity level and human-readable description.
Add new rules here; the checker picks them up automatically.
"""

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class Rule:
    pattern: str
    level: Literal["warning", "error"]
    rule: str         # unique rule code shown in compliance reports
    description: str


RULES: list[Rule] = [
    # ── Error level: hard regulatory violations ───────────────────────────────

    Rule(
        pattern=r"(保证|确保|一定|必定).{0,15}(盈利|正收益|收益率|涨|赚钱|不亏)",
        level="error",
        rule="PRO_001",
        description="禁止承诺或暗示投资收益",
    ),
    Rule(
        pattern=r"必涨|必定上涨|必跌|必定下跌|稳赚|稳赚不赔|零风险|无风险|100%(?:盈利|收益|上涨)",
        level="error",
        rule="PRO_002",
        description="禁止使用绝对化预测表述",
    ),
    Rule(
        pattern=r"内部消息|内幕(?:消息|信息|交易)|小道消息|未公开(?:信息|消息|数据)|独家内部",
        level="error",
        rule="PRO_003",
        description="禁止引用或暗示非公开信息",
    ),
    Rule(
        pattern=r"亏损.{0,8}(不可能|绝对不会|一定不会|不会发生)",
        level="error",
        rule="PRO_004",
        description="禁止否认亏损可能性",
    ),
    Rule(
        pattern=r"(?:本报告|本研究|分析师|我们).{0,20}(?:保证|承诺|确保).{0,10}(?:准确|正确|盈利|无误)",
        level="error",
        rule="PRO_005",
        description="禁止对研究报告准确性或投资结果作出担保",
    ),
    Rule(
        pattern=r"跟着(?:我|我们|本报告)(?:买|操作|投资).{0,10}(?:赚|盈|获利)",
        level="error",
        rule="PRO_006",
        description="禁止诱导性收益表述",
    ),

    # ── Warning level: require additional risk disclosure ─────────────────────

    Rule(
        pattern=r"(?:建议|推荐|应该|可以).{0,15}(?:立刻|马上|现在|尽快).{0,10}(?:买入|买进|加仓|满仓|建仓)",
        level="warning",
        rule="PRW_001",
        description="紧迫性投资操作建议须附风险提示",
    ),
    Rule(
        pattern=r"(?:强烈|极力|大力)(?:推荐|建议).{0,10}(?:买入|持有|加仓)",
        level="warning",
        rule="PRW_002",
        description="强烈程度措辞的投资建议须附风险提示",
    ),
    Rule(
        pattern=r"(?:目标价|目标价格|价格目标).{0,5}\d+(?:\.\d+)?(?:元|块|美元|港元)",
        level="warning",
        rule="PRW_003",
        description="给出具体目标价须说明分析依据及风险",
    ),
]
