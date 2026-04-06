# Intelligent Q&A Knowledge Retrieval Platform Resume Upgrade Checklist

## 1. 功能
- [x] 聊天 / 工具调用 / PDF RAG / 会话历史
- [x] 异步 ingestion（队列、重试、幂等、状态查询）
- [x] 多文档检索、重排、引用来源
- [x] API Key 生命周期策略继续细化（轮换/吊销/过期）
- [x] 多租户隔离（tenant 维度 API Key、审计、限流）
- [x] 模型路由（economy/balanced/quality）

## 2. 工程化
- [x] JWT + API Key + RBAC + 限流 + 审计
- [x] Flyway 迁移 + Docker + CI + 回归评测
- [x] 分布式压测脚本与演练脚本
- [x] 观测联调 runbook（Prometheus/Loki/Tempo/Alertmanager）
- [x] 演练报告模板与 k6 报告生成脚本
- [ ] 真实多节点演练结果沉淀（报告 + 图表证据）

## 3. README
- [x] 工程化定位
- [x] 增加改造清单入口
- [x] 重构为企业级平台口径（去除临时项目定位）
- [x] 增加企业部署与架构文档入口
- [x] 增加压测结果章节（p95/吞吐/错误率）
- [ ] 增加告警闭环截图章节

## 4. 测试
- [x] Controller / Service / Security / Ingestion 测试
- [x] Regression dataset + report pipeline
- [x] ModelRouter 单元测试
- [ ] 更大规模多跳与幻觉评测集
