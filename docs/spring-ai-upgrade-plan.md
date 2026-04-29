# Spring AI 升级计划

> 目标：从 Spring AI 1.0.0-M6（里程碑版）升级到首个 GA 稳定版，同步评估 Spring Boot 版本约束，控制回归风险。

## 当前基线

| 组件 | 版本 | 渠道 |
|---|---|---|
| Spring Boot | 3.4.3 | Maven Central |
| Spring AI BOM | 1.0.0-M6 | Spring Milestones |
| Java | 17 | — |
| Maven | 3.9+ | — |

## 为什么当前使用 M6

项目启动时（2025年7月），1.0.0-M6 是功能最完整的 Spring AI 里程碑版本，提供了本项目依赖的全部核心能力：`ChatClient` 流式调用、`@Tool` 注解、`QuestionAnswerAdvisor` 检索增强、`PagePdfDocumentReader` PDF 解析、`TokenTextSplitter` 切片、`ChatMemory` 会话记忆、`SimpleVectorStore` / `pgvector` 双后端向量存储。M6 在 API 形态上已接近 GA，后续版本主要是稳定性和 bugfix。

## 当前 Spring AI API 使用面

升级前需要关注的模块和 API 调用点：

### ChatClient 流式调用

| 文件 | 关键 API | 升级风险 |
|---|---|---|
| `CommonConfiguration.java` | `ChatClient.builder().defaultAdvisors().build()` | 中 |
| `ChatController.java` | `chatClient.prompt().user().call().chatResponse()` | 中 |
| `CustomerServiceController.java` | `chatClient.prompt().user().call().entity()` | 中 |
| `RagAnswerService.java` | `chatClient.prompt().advisors(qaAdvisor).user().call()` | 中 |
| `ReactAgentService.java` | `chatClient.prompt().user().stream().chatResponse()` | 高 |

### Advisor（检索增强 / 记忆 / 日志）

| 文件 | 关键 API | 升级风险 |
|---|---|---|
| `CommonConfiguration.java` | `QuestionAnswerAdvisor`, `MessageChatMemoryAdvisor`, `SimpleLoggerAdvisor` | 中 |
| `MysqlChatMemory.java` | `ChatMemory` 接口实现 | 低 |

### Tool Calling

| 文件 | 关键 API | 升级风险 |
|---|---|---|
| `CourseTools.java` | `@Tool(description=...)`, `@ToolParam(description=...)` | 中 |
| `CourseQuery.java` | `@ToolParam` | 低 |

### Vector Store

| 文件 | 关键 API | 升级风险 |
|---|---|---|
| `VectorStoreConfiguration.java` | `SimpleVectorStore`, `OpenAiEmbeddingModel` | 中 |
| `IngestionService.java` | `VectorStore.add(List<Document>)` | 低 |
| `RagAnswerService.java` | `VectorStore.similaritySearch(SearchRequest)` | 低 |

### PDF 文档读取与切片

| 文件 | 关键 API | 升级风险 |
|---|---|---|
| `IngestionService.java` | `PagePdfDocumentReader`, `PdfDocumentReaderConfig`, `ExtractedTextFormatter`, `TokenTextSplitter`, `Document` | 中 |

### 模型与多模态

| 文件 | 关键 API | 升级风险 |
|---|---|---|
| `CommonConfiguration.java` | `OpenAiChatModel`, `OllamaChatModel`, `ChatOptions` | 中 |
| `ChatController.java` | `Media`（附件多模态） | 低 |
| `MessageVO.java` | `Message`（消息体抽象） | 低 |

## 目标版本

| 候选版本 | 状态 | 约束 | 建议 |
|---|---|---|---|
| 1.0.0-M7+ | 后续里程碑 | 可能引入更多 API 变化 | 如果 GA 未出，可先升到最新 M 版本减少差距 |
| 1.0.0 GA | 首个稳定版 | 与 M6 之间可能有 breaking changes | 理想目标 |
| 1.0.x GA | 首个稳定版 + patch | 最安全 | 建议等至少 1 个 patch 后再升 |

建议：等待 1.0.0 GA 发布后至少 2 周，确认社区没有严重回归报告，再执行升级。

## 分步升级方案

### Step 1：独立分支验证

```bash
git checkout -b upgrade/spring-ai-ga
```

修改 `pom.xml`：

```xml
<spring-ai.version>1.0.0</spring-ai.version>  <!-- 替换为实际 GA 版本号 -->
```

同时检查是否需要移除 `spring-milestones` repository（GA 发布后应从 Maven Central 获取）。

### Step 2：编译与 API 适配

```bash
mvn -DskipTests compile
```

按优先级处理编译错误：

| 优先级 | 模块 | 常见变化 |
|---|---|---|
| P0 | `ChatClient.Builder` chain | builder 方法重命名、defaultAdvisors 签名变化 |
| P0 | `@Tool` / `@ToolParam` | 注解属性名或默认值变化 |
| P1 | `QuestionAnswerAdvisor` | 构造函数参数顺序或 SearchRequest 绑定方式 |
| P1 | `PagePdfDocumentReader` | reader 配置 API 调整 |
| P1 | `VectorStore` 接口 | 方法签名变化 |
| P2 | `ChatOptions` | 新增/废弃的 option key |
| P2 | `Media` | 多模态构造方式 |
| P3 | `ChatMemory` / `Message` | 通常向后兼容 |

### Step 3：单元测试

```bash
mvn test
```

### Step 4：集成测试（含 Testcontainers）

```bash
mvn verify -Pintegration-test
```

### Step 5：回归评测

```bash
python3 scripts/generate_eval_predictions.py
python3 scripts/run_regression.py \
  --dataset evaluation/dataset.large.json \
  --predictions evaluation/predictions.generated.json \
  --threshold 0.75
```

对比升级前后分数：

| 指标 | 升级前 | 升级后 | 变化 |
|---|---|---|---|
| Answer correctness | — | — | — |
| Citation hit rate | — | — | — |
| Empty-result handling | — | — | — |

### Step 6：端到端 smoke

```bash
./scripts/demo.sh
./scripts/demo.sh verify
```

### Step 7：更新文档

- `README.md`：技术栈表中 Spring AI 版本号
- `docs/operations.md`：如有队列或向量存储配置变化
- 本文件：补充实际升级过程中的发现

## 回滚策略

1. **镜像回滚**：升级前记录当前 `v1.0.0` Docker 镜像 SHA，确保 `docker compose up` 可退回上一版本。
2. **分支保护**：`upgrade/spring-ai-ga` 分支通过完整 CI（编译 + 单测 + 集成测试 + 回归评测 + E2E smoke）前不合入 `main`。
3. **回归门槛**：回归评测中 answer correctness 和 citation hit rate 任一下降超过 5%，暂缓升级，将差异上报到 Spring AI issue tracker 后再决定。
4. **数据库兼容**：Flyway 迁移脚本保持独立，升级不新增迁移（除非向量存储 schema 有强制变化）。

## 里程碑仓库清理

Spring Milestones repository (`https://repo.spring.io/milestone`) 在升级到 GA 后应从 `pom.xml` 的 `<repositories>` 块中移除。GA 版本通过 Maven Central 分发，不再需要 milestone repo。

## 追踪

- Spring AI Releases：[https://github.com/spring-projects/spring-ai/releases](https://github.com/spring-projects/spring-ai/releases)
- Spring AI 迁移指南：[https://docs.spring.io/spring-ai/reference/](https://docs.spring.io/spring-ai/reference/)
- Spring Boot 兼容矩阵：[https://spring.io/projects/spring-boot#support](https://spring.io/projects/spring-boot#support)

## 记录

- 计划制定：2026-04-29
- 升级执行：待 Spring AI 1.0.0 GA 发布
- 执行人：待定
