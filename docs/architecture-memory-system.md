# 长短期记忆系统设计

## 四层记忆模型

```
┌─────────────────────────────────────────────┐
│ short_memory  会话最近 N 轮，TTL 24h          │
├─────────────────────────────────────────────┤
│ long_memory   用户画像/偏好/目标，跨会话持久化  │
├─────────────────────────────────────────────┤
│ task_memory   某次研究/客服任务的中间结论       │
├─────────────────────────────────────────────┤
│ fact_memory   可引用、可追溯的事实，带置信度     │
└─────────────────────────────────────────────┘
```

## 设计决策

### 单表继承 vs 多表
所有记忆类型共用 `memory_item` 表，通过 `type` 字段区分。好处：
- 不需要多表 JOIN
- 统一过期管理
- 扩展新记忆类型只需加 type 枚举值

### 何时分表
当某种记忆类型数据量超过千万级，或有特殊索引需求时，可按 type 分表。

## 数据库设计

### memory_item
| 字段 | 说明 |
|---|---|
| memory_id | 全局唯一记忆 ID |
| type | short / long / task / fact |
| content | 记忆内容 |
| source | 来源标注（会话 ID、任务 ID、文档来源） |
| source_task_id | 关联任务 ID（task_memory 专用） |
| confidence | 可信度 (0-1)，低于阈值的不会进入生成上下文 |
| expires_at | 过期时间，NULL 表示永不过期 |
| metadata_json | 扩展元数据 |

### memory_event
| 字段 | 说明 |
|---|---|
| action | CREATE / UPDATE / DELETE / EXPIRE / HIT / USE |
| reason | 操作原因 |

## MemoryService API

| 方法 | 说明 |
|---|---|
| `saveShortMemory()` | 保存短期记忆，默认 TTL 24h |
| `saveLongMemory()` | 保存长期记忆，永不过期 |
| `saveTaskMemory()` | 保存任务记忆，关联 task_id，TTL 30d |
| `saveFactMemory()` | 保存事实记忆，带置信度 |
| `queryShortMemory()` | 查询最近 N 条短期记忆 |
| `queryLongMemory()` | 查询用户长期记忆 |
| `queryTaskMemory()` | 按 taskId 查询任务记忆 |
| `queryFactMemory()` | 按置信度阈值查询事实 |
| `buildContext()` | 构建记忆上下文（拼接到 system prompt） |
| `cleanExpiredMemories()` | 定时清理过期记忆（每天 3am） |

## 记忆写入时机

| 时机 | 记忆类型 | 内容 |
|---|---|---|
| 每轮对话结束 | short | 本轮用户问题 + 系统回答摘要 |
| 用户首次注册/配置 | long | 用户画像、偏好、学习目标 |
| Agent 任务完成 | task | 研究中间结论、客服处理方案 |
| RAG 检索到高置信文档 | fact | 抽取的实体-关系-值三元组 |

## 记忆召回流程

1. 用户发起请求
2. `buildContext(tenantId, userId)` 检索相关记忆
3. 召回内容拼接到 LLM system prompt 或 user prompt
4. 在 SSE 事件中通过 MEMORY(1007) 事件标记记忆命中
5. 本轮结束后写入新的 short memory

## 自动过期

```sql
DELETE FROM memory_item
WHERE expires_at IS NOT NULL AND expires_at < NOW()
```

由 Spring `@Scheduled(cron = "0 0 3 * * ?")` 每天凌晨 3 点执行。
