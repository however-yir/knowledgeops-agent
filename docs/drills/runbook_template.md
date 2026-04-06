# Fault Drill Runbook Template

## 1. Drill Metadata

- Drill Name:
- Date:
- Operator:
- Environment:
- Version / Commit:

## 2. Objective

- Primary SLO/SLA objective:
- Hypothesis:
- Success criteria:

## 3. Scope and Preconditions

- Services in scope:
- Dependencies in scope:
- Baseline metrics snapshot completed: `yes/no`
- Stakeholders notified: `yes/no`
- Rollback owner confirmed: `yes/no`

## 4. Drill Procedure

1. Start time:
2. Trigger action:
3. Observe key metrics:
4. Observe logs/traces:
5. Validate alerting path:
6. Recovery action:
7. End time:

## 5. Evidence

- Dashboard screenshots:
- Alert screenshots (firing + resolved):
- Trace IDs:
- Key log snippets:
- k6 summary/report paths:
  - `reports/performance/distributed-k6-summary.json`
  - `reports/performance/k6-report.md`

## 6. Results

| Indicator | Baseline | Drill Peak | Target | Result |
|---|---:|---:|---:|---|
| p95 latency (ms) |  |  |  |  |
| error rate (%) |  |  |  |  |
| queue lag |  |  |  |  |
| ingestion failure ratio (%) |  |  |  |  |

## 7. Findings and Follow-up

- What worked:
- What failed:
- Root cause:
- Follow-up actions:
- Owner and due date:
