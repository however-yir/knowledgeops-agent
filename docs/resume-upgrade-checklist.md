# ai-demo Resume Upgrade Checklist

## 1. 功能
- [x] 聊天 / 工具调用 / PDF RAG / 会话历史
- [x] 异步 ingestion（队列、重试、幂等、状态查询）
- [x] 多文档检索、重排、引用来源
- [ ] API Key 生命周期策略继续细化（轮换/吊销/过期）

## 2. 工程化
- [x] JWT + API Key + RBAC + 限流 + 审计
- [x] Flyway 迁移 + Docker + CI + 回归评测
- [x] 分布式压测脚本与演练脚本
- [x] 观测联调 runbook（Prometheus/Loki/Tempo/Alertmanager）
- [ ] 真实多节点演练结果沉淀（报告 + 图表证据）

## 3. README
- [x] 工程化定位
- [x] 增加改造清单入口
- [ ] 增加压测结果章节（p95/吞吐/错误率）
- [ ] 增加告警闭环截图章节

## 4. 测试
- [x] Controller / Service / Security / Ingestion 测试
- [x] Regression dataset + report pipeline
- [ ] 更大规模多跳与幻觉评测集
