from app.core.logging import get_logger
from app.models.agent_task import AgentRole, ExecutionMode, TaskPlan, TaskStep, TaskStatus
from app.models.decision import AgentDecision

logger = get_logger(__name__)


class PlannerAgent:
    """Builds a structured complex-task plan from refined query analysis."""

    def create_plan(self, query: str, decision: AgentDecision) -> TaskPlan:
        sub_queries = decision.query_analysis.sub_queries or [
            decision.action.tool_args.get("query", query)
        ]

        steps: list[TaskStep] = [
            TaskStep(
                step_id="planner",
                role=AgentRole.PLANNER,
                instruction="根据 refined query analysis 生成复杂任务执行计划",
                status=TaskStatus.COMPLETED,
                input_payload={
                    "query": query,
                    "query_analysis": decision.query_analysis.model_dump(),
                },
                output_payload={
                    "route": decision.query_analysis.route.value,
                    "sub_queries": sub_queries,
                },
            )
        ]

        for idx, sub_query in enumerate(sub_queries, start=1):
            steps.append(
                TaskStep(
                    step_id=f"retrieval_{idx}",
                    role=AgentRole.RETRIEVER,
                    instruction=f"检索子问题 {idx} 的证据片段",
                    input_payload={
                        "query": sub_query,
                        "tool_name": decision.action.tool_name,
                        "top_k": decision.action.tool_args.get("top_k", 5),
                    },
                )
            )

        steps.append(
            TaskStep(
                step_id="writer",
                role=AgentRole.WRITER,
                instruction="基于多子查询证据生成最终带引用回答",
                input_payload={
                    "query": query,
                    "sub_query_count": len(sub_queries),
                },
            )
        )
        steps.append(
            TaskStep(
                step_id="compliance",
                role=AgentRole.COMPLIANCE,
                instruction="记录最终回答的合规检查结果",
            )
        )

        logger.info("planner_plan_created", sub_query_count=len(sub_queries))
        return TaskPlan(
            query=query,
            query_analysis=decision.query_analysis,
            execution_mode=ExecutionMode.COMPLEX_ORCHESTRATED,
            steps=steps,
        )
