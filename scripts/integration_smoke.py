import asyncio
import json
import uuid

from qdrant_client.models import PointStruct

from app.agent.agent_loop import run_agent
from app.core.qdrant_client import ensure_collections, get_qdrant
from app.core.request_context import RequestContext
from app.doc_pipeline.embedder import embed_texts

TEXT = """贵州茅台研究纪要

一、核心结论
我们认为公司2024年营收约为1700亿元，利润表现保持稳健，增长主要由高端产品结构升级和渠道优化共同驱动。

二、关键指标
2024年营收：1700亿元。
2024年归母净利润：850亿元。
毛利率维持高位。

三、增长驱动
1. 高端产品结构升级提升单价和盈利能力。
2. 渠道优化改善经销效率与终端覆盖。
3. 品牌力增强带来需求韧性。

四、风险提示
如果消费需求走弱，或渠道库存上升，增长可能低于预期。
"""


async def main() -> None:
    await ensure_collections()

    vector = (await embed_texts([TEXT]))[0]
    request_id = f"integration-{uuid.uuid4()}"
    context = RequestContext(
        user_id="demo-user",
        tenant_id="demo-tenant",
        request_id=request_id,
        channel="integration-test",
    )
    document_id = f"demo-doc-{uuid.uuid4()}"
    point = PointStruct(
        id=str(uuid.uuid4()),
        vector=vector,
        payload={
            "document_id": document_id,
            "tenant_id": context.tenant_id,
            "owner_user_id": context.user_id,
            "text": TEXT,
            "page_num": 2,
            "section_title": "关键指标",
        },
    )
    await get_qdrant().upsert(collection_name="documents", points=[point])

    events = []
    async for event in run_agent(
        session_id="demo-tenant:demo-user:integration-session",
        user_message="根据已上传文档，贵州茅台2024年营收是多少，并简要说明增长驱动因素。",
        context=context,
    ):
        events.append(event.model_dump())

    print(
        json.dumps(
            {
                "request_id": request_id,
                "document_id": document_id,
                "events": events,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
