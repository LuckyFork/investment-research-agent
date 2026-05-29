export type Locale = "zh" | "en";

export const messages = {
  zh: {
    topbar: {
      title: "Agent 控制台",
      subtitle: "Adaptive-RAG · 多 Agent · 回放/评测",
      console: "控制台",
      traces: "轨迹",
      evals: "评测",
      language: "语言",
      zh: "中文",
      en: "英文"
    },
    console: {
      conversation: "对话",
      conversationHint: "流式展示问答、工具调用和合规事件。",
      queryAnalysis: "查询分析",
      toolTimeline: "工具时间线",
      toolTimelineHint: "展示检索过程与证据收集步骤。",
      taskPlan: "任务计划",
      traceSummary: "轨迹摘要",
      evidence: "证据",
      compliance: "合规",
      currentStatus: "当前状态",
      noCompliance: "暂无合规结果",
      passed: "通过",
      blocked: "阻断"
    },
    chat: {
      sessionId: "会话 ID",
      placeholder: "请输入研究问题...",
      runQuery: "运行查询",
      streaming: "流式处理中...",
      statusStreaming: "Agent 正在流式输出事件...",
      statusReady: "可以开始下一次查询了。",
      noConversation: "暂无对话",
      noConversationBody: "运行一条查询来查看完整的 Agent 执行链路。"
    },
    trace: {
      recentTraces: "最近轨迹",
      loadingSummaries: "正在加载轨迹摘要...",
      noTraces: "暂无轨迹",
      noTracesBody: "从控制台运行一条复杂查询来生成回放产物。",
      traceHeader: "轨迹头部",
      loadingDetail: "正在加载轨迹详情...",
      traceNotFound: "未找到轨迹",
      traceNotFoundBody: "请从轨迹列表中选择有效轨迹。",
      analysis: "分析",
      taskSteps: "任务步骤",
      evidenceAndAnswer: "证据与回答",
      finalAnswer: "最终回答",
      noAnswer: "暂无回答",
      traceId: "轨迹 ID",
      stepCount: "{count} 个步骤",
      answerPreview: "回答预览",
      noPreview: "暂无预览",
      fallbackTriggered: "已触发回退",
      unknownReason: "未知原因",
      viewFullTrace: "查看完整轨迹"
    },
    eval: {
      summary: "评测摘要",
      cases: "评测用例",
      loadingSummary: "正在加载评测摘要...",
      loadingDetails: "正在加载评测明细...",
      noSummary: "暂无评测摘要",
      noSummaryBody: "运行 scripts/run_eval.py 生成最新 benchmark 产物。",
      noDetails: "暂无评测明细",
      noDetailsBody: "生成 latest-details.json 后可查看逐题结果。",
      table: {
        case: "用例",
        route: "路由",
        doc: "文档",
        page: "页码",
        keywords: "关键词"
      },
      cards: {
        cases: "样例数",
        route: "路由准确率",
        documentHit: "文档命中",
        pageHit: "页码命中",
        keywordHit: "关键词命中",
        compliance: "合规"
      }
    },
    empty: {
      noQueryAnalysis: "暂无查询分析",
      noQueryAnalysisBody: "复杂查询完成后，这里会出现分析元数据。",
      noToolActivity: "暂无工具活动",
      noToolActivityBody: "Agent 检索证据时，这里会展示 tool start/done 事件。",
      noTaskPlan: "暂无任务计划",
      noTaskPlanBody: "复杂路由完成后，这里会出现任务步骤。",
      noTraceSummary: "暂无轨迹摘要",
      noTraceSummaryBody: "Agent 运行完成后，这里会加载最新轨迹摘要。",
      noEvidence: "暂无证据",
      noEvidenceBody: "有轨迹后，这里会展示检索证据预览。",
      noRetrievalSteps: "暂无检索步骤",
      noRetrievalStepsBody: "当前运行没有产生 retriever 证据卡片。"
    },
    analysis: {
      reasons: "原因",
      subQueries: "子查询",
      noReasons: "暂无原因",
      none: "无",
      confidence: "置信度",
      unknown: "未知",
      source: "来源"
    },
    task: {
      planner: "规划器",
      retriever: "检索器",
      writer: "写作器",
      compliance: "合规器",
      completed: "已完成",
      running: "进行中",
      failed: "失败",
      fallback: "回退",
      pending: "待执行",
      skipped: "已跳过"
    },
    route: {
      direct_retrieval: "直接检索",
      summary_retrieval: "摘要检索",
      multi_hop_aggregation: "多跳聚合"
    },
    complexity: {
      simple: "简单",
      summary: "总结",
      complex: "复杂"
    },
    source: {
      rule: "规则",
      llm_refined: "LLM 复判",
      rule_fallback_low_confidence: "规则回退（低置信度）",
      rule_fallback_guardrail: "规则回退（守护策略）",
      rule_fallback_exception: "规则回退（异常）"
    },
    tool: {
      toolStart: "开始调用",
      toolDone: "调用完成",
      hitCount: "命中 {count} 条",
      topScore: "最高分 {score}",
      page: "第{page}页",
      score: "分数 {score}"
    },
    evidence: {
      hitCount: "命中 {count} 条",
      topScore: "最高分 {score}",
      noPreview: "暂无结果预览",
      expand: "展开",
      collapse: "收起"
    },
    common: {
      yes: "是",
      no: "否",
      na: "--",
      updatedAt: "更新时间",
      sessionId: "会话 ID",
      query: "查询"
    }
  },
  en: {
    topbar: {
      title: "Agent Console",
      subtitle: "Adaptive-RAG · Multi-Agent · Replay/Eval",
      console: "Console",
      traces: "Traces",
      evals: "Evals",
      language: "Language",
      zh: "中文",
      en: "English"
    },
    console: {
      conversation: "Conversation",
      conversationHint: "Stream answers, tool calls, and compliance events.",
      queryAnalysis: "Query Analysis",
      toolTimeline: "Tool Timeline",
      toolTimelineHint: "Shows retrieval activity and evidence collection steps.",
      taskPlan: "Task Plan",
      traceSummary: "Trace Summary",
      evidence: "Evidence",
      compliance: "Compliance",
      currentStatus: "Current status",
      noCompliance: "No compliance result yet",
      passed: "Passed",
      blocked: "Blocked"
    },
    chat: {
      sessionId: "Session ID",
      placeholder: "Ask a research question...",
      runQuery: "Run Query",
      streaming: "Streaming...",
      statusStreaming: "Agent is streaming events...",
      statusReady: "Ready for the next query.",
      noConversation: "No conversation yet",
      noConversationBody: "Run a query to inspect the full agent execution flow."
    },
    trace: {
      recentTraces: "Recent Traces",
      loadingSummaries: "Loading trace summaries...",
      noTraces: "No traces found",
      noTracesBody: "Run a complex query from the console to generate replay artifacts.",
      traceHeader: "Trace Header",
      loadingDetail: "Loading trace detail...",
      traceNotFound: "Trace not found",
      traceNotFoundBody: "Select a valid trace from the trace list.",
      analysis: "Analysis",
      taskSteps: "Task Steps",
      evidenceAndAnswer: "Evidence and Answer",
      finalAnswer: "Final Answer",
      noAnswer: "No answer available",
      traceId: "Trace ID",
      stepCount: "{count} steps",
      answerPreview: "Answer Preview",
      noPreview: "No preview available",
      fallbackTriggered: "Fallback triggered",
      unknownReason: "Unknown reason",
      viewFullTrace: "View full trace"
    },
    eval: {
      summary: "Eval Summary",
      cases: "Eval Cases",
      loadingSummary: "Loading eval summary...",
      loadingDetails: "Loading eval details...",
      noSummary: "No eval summary",
      noSummaryBody: "Run scripts/run_eval.py to generate the latest benchmark artifacts.",
      noDetails: "No eval details",
      noDetailsBody: "Generate latest-details.json to inspect per-case results.",
      table: {
        case: "Case",
        route: "Route",
        doc: "Doc",
        page: "Page",
        keywords: "Keywords"
      },
      cards: {
        cases: "Cases",
        route: "Route",
        documentHit: "Document Hit",
        pageHit: "Page Hit",
        keywordHit: "Keyword Hit",
        compliance: "Compliance"
      }
    },
    empty: {
      noQueryAnalysis: "No query analysis",
      noQueryAnalysisBody: "Analysis metadata will appear here after a complex run completes.",
      noToolActivity: "No tool activity",
      noToolActivityBody: "Tool start/done events will appear here as the agent retrieves evidence.",
      noTaskPlan: "No task plan",
      noTaskPlanBody: "Task steps will populate here after a complex route finishes.",
      noTraceSummary: "No trace summary",
      noTraceSummaryBody: "The latest trace summary will load here after the agent run finishes.",
      noEvidence: "No evidence yet",
      noEvidenceBody: "Retriever output previews will appear here once a trace is available.",
      noRetrievalSteps: "No retrieval steps",
      noRetrievalStepsBody: "This run did not produce retriever evidence cards."
    },
    analysis: {
      reasons: "Reasons",
      subQueries: "Sub Queries",
      noReasons: "No reasons available",
      none: "None",
      confidence: "confidence",
      unknown: "unknown",
      source: "source"
    },
    task: {
      planner: "planner",
      retriever: "retriever",
      writer: "writer",
      compliance: "compliance",
      completed: "completed",
      running: "running",
      failed: "failed",
      fallback: "fallback",
      pending: "pending",
      skipped: "skipped"
    },
    route: {
      direct_retrieval: "direct retrieval",
      summary_retrieval: "summary retrieval",
      multi_hop_aggregation: "multi-hop aggregation"
    },
    complexity: {
      simple: "simple",
      summary: "summary",
      complex: "complex"
    },
    source: {
      rule: "rule",
      llm_refined: "LLM refined",
      rule_fallback_low_confidence: "rule fallback (low confidence)",
      rule_fallback_guardrail: "rule fallback (guardrail)",
      rule_fallback_exception: "rule fallback (exception)"
    },
    tool: {
      toolStart: "tool_start",
      toolDone: "tool_done",
      hitCount: "{count} hits",
      topScore: "Top score {score}",
      page: "Page {page}",
      score: "score {score}"
    },
    evidence: {
      hitCount: "{count} hits",
      topScore: "Top score {score}",
      noPreview: "No result preview",
      expand: "Expand",
      collapse: "Collapse"
    },
    common: {
      yes: "Yes",
      no: "No",
      na: "--",
      updatedAt: "Updated",
      sessionId: "Session ID",
      query: "Query"
    }
  }
} as const;
