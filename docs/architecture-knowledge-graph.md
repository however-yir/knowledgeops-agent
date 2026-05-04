# 知识图谱设计

## 为什么用 MySQL 做轻量图谱

选择 MySQL 邻接表而非 Neo4j 的原因：
1. 零新增基础设施：复用已有 MySQL，不需要额外图数据库
2. 一跳/两跳查询足够：当前业务场景主要是实体搜索和一跳邻居
3. 可迁移：数据模型（entity → relation → entity）可直接映射到 Neo4j 或 ArangoDB

当需要 >3 跳遍历或千万级实体时，迁移到专用图数据库。

## 表结构

### kg_entity（实体）
| 字段 | 说明 |
|---|---|
| entity_id | 全局唯一实体 ID |
| name | 实体名称 |
| type | COURSE / SKILL_LEVEL / TOPIC / CONCEPT |
| aliases | JSON 数组，支持别名搜索 |
| description | 实体描述 |
| source_id | 来源（PDF chunk ID、课程 ID 等） |

### kg_relation（关系）
| 字段 | 说明 |
|---|---|
| source_entity_id | 源实体 |
| target_entity_id | 目标实体 |
| relation_type | REQUIRES_LEVEL / BELONGS_TO / PREREQUISITE_FOR |
| weight | 关系权重 (0-1) |
| evidence_id | 支撑证据（文档 chunk ID） |

### kg_fact（事实）
| 字段 | 说明 |
|---|---|
| subject / predicate / object | SPO 三元组 |
| confidence | 可信度 (0-1) |
| valid_from / valid_to | 时效性 |
| source | 来源标注 |

## 种子数据

内置课程图谱种子数据：

```
Java编程实战 --REQUIRES_LEVEL--> 零基础入门
Java编程实战 --BELONGS_TO--> 后端开发
Python数据分析 --REQUIRES_LEVEL--> 零基础入门
Python数据分析 --BELONGS_TO--> 数据科学
Spring Boot微服务 --REQUIRES_LEVEL--> 中级进阶
Spring Boot微服务 --BELONGS_TO--> 后端开发
Java编程实战 --PREREQUISITE_FOR--> Spring Boot微服务
```

## 查询能力

### 实体搜索
```sql
SELECT * FROM kg_entity
WHERE name LIKE '%Java%'
   OR JSON_CONTAINS(aliases, '"Java"')
```

### 一跳邻居
```sql
SELECT e.*, r.relation_type, r.weight
FROM kg_relation r
JOIN kg_entity e ON e.entity_id = r.target_entity_id
WHERE r.source_entity_id = 'ent-course-java'
```

### 事实检索
```sql
SELECT * FROM kg_fact
WHERE subject LIKE '%Spring%' OR object LIKE '%Spring%'
ORDER BY confidence DESC
```

## GraphService API

| 方法 | 说明 |
|---|---|
| `searchEntities(tenantId, keyword, limit)` | 按名称/别名搜索实体 |
| `getNeighbors(tenantId, entityId)` | 获取一跳邻居 + 关系类型 |
| `searchFacts(tenantId, keyword, limit)` | 搜索事实三元组 |
| `getEntitiesByType(tenantId, type)` | 按类型列出实体 |

## 扩展路径

1. **文档图谱**：从 PDF chunk 中抽取实体和关系，自动填充 kg_entity/kg_relation
2. **课程图谱**：课程、难度、前置知识、适合人群、讲师、后续路径
3. **多跳推理**：2-3 跳查询发现间接关联（如：Python → 数据科学 → 机器学习课程）
