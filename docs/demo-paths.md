# V1 演示路径

三条固定演示链路，覆盖 KnowledgeOps Agent 的全部核心能力。每条链路 3-5 分钟可完成。

## 链路一：DeepResearch 行业研究

**展示能力**：AgentWorkflowEngine → ResearchPlannerAgent → 混合检索 → EvidenceJudgeAgent → ReportWriterAgent

**演示步骤**：

```bash
# 1. 启动服务
./scripts/demo.sh

# 2. 创建研究任务
curl -X POST http://localhost:8080/ai/research/tasks \
  -H "Content-Type: application/json" \
  -H "X-Tenant-Id: public" \
  -d '{
    "topic": "2025年AI Agent在企業服務領域的應用趨勢",
    "enableWebSearch": false,
    "enableRagSearch": true,
    "enableGraphSearch": true,
    "maxSearchRounds": 3
  }'

# 3. 查询任务状态与步骤
curl http://localhost:8080/ai/research/tasks/{taskId} \
  -H "X-Tenant-Id: public"

# 4. 获取研究报告
curl http://localhost:8080/ai/research/tasks/{taskId}/report \
  -H "X-Tenant-Id: public"
```

**验证点**：
| 检查项 | 预期结果 |
|---|---|
| 任务创建 | 返回 taskId，status=CREATED→PLANNING→...→DONE |
| 主题拆解 | agent_step 中 ResearchPlannerAgent 输出 3-5 个子问题 |
| 检索召回 | 每个子问题触发混合检索（vector + keyword + graph） |
| 证据评分 | evidence 数组中每条记录带 relevanceScore/authorityScore/timelinessScore |
| 报告生成 | final_output 包含 Executive Summary、Key Findings、Detailed Analysis |
| 事件溯源 | GET /tasks/{taskId}/events 返回完整 STATE_CHANGED/STEP_STARTED/STEP_COMPLETED 序列 |

## 链路二：智能客服（通过 tianji-ai-agent）

**展示能力**：tianji RouteAgent（结构化 JSON 意图识别）→ 9 种子 Agent → Tool Calling → KnowledgeOpsClient（RAG/记忆/图谱）→ SSE 全链路事件

**演示步骤**：

```bash
# 1. 启动 tianji（dev-demo 模式）
cd tianji-ai-agent
bash scripts/quick-start-mac.sh

# 2. 打开 http://localhost:5173

# 3. 依次输入以下问题：
```

| 场景 | 输入 | 预期路由 | 预期事件 |
|---|---|---|---|
| 课程推荐 | "我零基础，想 3 个月入门 Java 后端，帮我推荐课程" | ROUTE→RECOMMEND | ROUTE(1004)→DATA(1001)→PARAM(1003)→STOP(1002) |
| 课程咨询 | "1589905661084430337 这门课适合谁，价格多少" | ROUTE→CONSULT | ROUTE→DATA→PARAM(courseInfo)→STOP |
| 预下单 | "我要购买课程 1589905661084430337，帮我生成确认订单" | ROUTE→BUY | ROUTE→DATA→PARAM(prePlaceOrder)→STOP |
| 知识问答 | "Java 中 Redis 缓存穿透是什么" | ROUTE→KNOWLEDGE | ROUTE→DATA→STOP |
| 转人工 | "我要投诉课程质量问题" | ROUTE→COMPLAINT 或 HUMAN_HANDOFF | ROUTE→DATA→STOP |

**验证点**：
| 检查项 | 预期结果 |
|---|---|
| 路由 JSON | RouteAgent 返回 `{"intent":"BUY","confidence":0.91,"nextAgent":"BUY",...}` |
| 卡片渲染 | 前端展示课程卡片、订单卡片、引用来源 |
| SSE 事件序列 | ROUTE→DATA→PARAM→STOP 完整链路 |
| 记忆命中 | 第二轮对话时 MEMORY 事件出现 |

## 链路三：知识库问答（混合检索 + 引用溯源）

**展示能力**：PDF 上传 → 异步入库 → VectorRetriever + KeywordRetriever + GraphRetriever → EvidenceJudgeService → CitationService

**演示步骤**：

```bash
# 1. 上传 PDF 到知识库
curl -X POST http://localhost:8080/ai/pdf/upload/demo-chat-1 \
  -H "X-Tenant-Id: public" \
  -F "file=@docs/assets/sample.pdf"

# 2. 等待入库完成（查询 ingestion job 状态）
curl http://localhost:8080/ingestion/jobs?chatId=demo-chat-1 \
  -H "X-Tenant-Id: public"

# 3. 混合检索问答
curl -X POST http://localhost:8080/ai/rag/search \
  -H "Content-Type: application/json" \
  -H "X-Tenant-Id: public" \
  -d '{
    "prompt": "文档中提到的核心概念是什么",
    "chatId": "demo-chat-1"
  }'

# 4. 通过工作流接口（带 trace）
curl -X POST http://localhost:8080/ai/workflow/react/chat \
  -H "Content-Type: application/json" \
  -H "X-Tenant-Id: public" \
  -d '{
    "prompt": "文档中提到的核心概念是什么",
    "chatId": "demo-chat-1",
    "modelProfile": "balanced"
  }'
```

**返回结构示例**：
```json
{
  "answer": "根據文檔分析，核心概念包括...",
  "citations": [
    {"index": 1, "sourceType": "vector", "title": "sample.pdf", "confidence": 0.92}
  ],
  "evidence": [
    {
      "sourceType": "vector",
      "title": "sample.pdf",
      "chunkId": "chunk-3",
      "score": 0.86,
      "relevanceScore": 0.92,
      "authorityScore": 0.75,
      "timelinessScore": 0.70,
      "reason": "向量语义匹配，相关度92%，权威度75%，时效度70%"
    }
  ],
  "traceId": "trace-a1b2c3d4",
  "memoryUsed": []
}
```

**验证点**：
| 检查项 | 预期结果 |
|---|---|
| PDF 上传 | 返回 jobId，状态 pending→running→success |
| 向量检索 | VectorRetriever 返回 topK 文档，score>0.45 |
| 关键词检索 | KeywordRetriever 返回标题/内容关键词匹配结果 |
| 图谱检索 | GraphRetriever 返回 kg_entity 匹配实体和一跳邻居 |
| 融合去重 | HybridRetrievalService 合并四路结果并去重 |
| 证据评分 | 每条 evidence 带三维评分和中文理由 |
| 引用溯源 | citations 数组带 index/sourceType/chunkId/confidence |
| 工作流追踪 | agent_task→agent_step→agent_event 完整链路可查 |

## 异常场景验证

| 场景 | 预期行为 |
|---|---|
| 知识库无匹配 | answer="没有在当前知识库中检索到可用内容"，pipelineOutcome=empty |
| 模型超时 | Resilience4j TimeLimiter 触发，返回降级回答 |
| 工具调用失败 | observation 中 status=error，不阻断流程 |
| 用户中断生成 | SSE stream 在 STOP 事件后正常关闭 |
| 重复提交 | ingestion 幂等键去重，不重复入库 |
