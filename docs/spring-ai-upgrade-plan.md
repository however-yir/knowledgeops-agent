# Spring AI 升级计划

> 目标：从 Spring AI 1.0.0-M6（已验证实现基线）升级到当前 1.1.x 稳定线，同步更新 starter 命名规范与 breaking API changes。

## 升级状态：🔄 进行中（API 迁移待完成）

Spring AI `1.0.0-M6` 保持为当前可复现演示基线。官方稳定线已经进入 `1.1.x`，但从 M6 迁移需要逐文件适配 API 与 starter 命名变化，不能只改 BOM 版本。

## 当前基线

| 组件 | 版本 | 渠道 |
|---|---|---|
| Spring Boot | 3.4.3 | Maven Central |
| Spring AI BOM | 1.0.0-M6 | Spring Milestones |
| Java | 17 | — |

## 1.1.x 迁移候选

| 组件 | 目标 |
|---|---|
| Spring AI BOM | 1.1.x stable line |
| Starter 命名 | `spring-ai-starter-*` |
| 验证标准 | `mvn -DskipTests compile`、`mvn test`、集成测试、demo smoke、回归评测 |

## 已知 Breaking Changes

| 原 API (M6) | 新 API (1.0+/1.1.x) | 影响文件 |
|---|---|---|
| `org.springframework.ai.chat.client.advisor.QuestionAnswerAdvisor` | `org.springframework.ai.chat.client.advisor.vectorstore.QuestionAnswerAdvisor` (新模块 `spring-ai-advisors-vector-store`) | `CommonConfiguration.java` |
| `org.springframework.ai.chat.client.advisor.AbstractChatMemoryAdvisor.CHAT_MEMORY_CONVERSATION_ID_KEY` | `org.springframework.ai.chat.client.advisor.api.BaseChatMemoryAdvisor.CHAT_MEMORY_CONVERSATION_ID_KEY` | `RagAnswerService.java`, `HybridRagAnswerService.java`, `ChatController.java`, `CustomerServiceController.java` |
| `org.springframework.ai.model.Media` | 待确认（已从 `spring-ai-model` 移出） | `ChatController.java` |
| `spring-ai-ollama-spring-boot-starter` | `spring-ai-starter-model-ollama` | `pom.xml` |
| `spring-ai-openai-spring-boot-starter` | `spring-ai-starter-model-openai` | `pom.xml` |
| `spring-ai-pgvector-store` | `spring-ai-starter-vector-store-pgvector` | `pom.xml` |

## 升级步骤

1. 在独立分支 `upgrade/spring-ai-1.1` 上逐文件适配 API 变化
2. 运行 `mvn -DskipTests compile` 确认编译通过
3. 运行 `mvn test` 确认单测通过
4. 运行 `mvn verify -Pintegration-test` 确认集成测试通过
5. 注册回归评测对比升级前后分数
6. 端到端 smoke 测试
7. 更新 README 和文档

## 记录

- 计划制定：2026-04-29
- 目标线更新：2026-05-22（从 GA 目标更新为 1.1.x 稳定线）
- API 迁移适配：待执行
- 执行人：however-yir
