package com.enterprise.iqk.evaluation;

import com.enterprise.iqk.evaluation.vo.EvalCaseCreateVO;
import com.enterprise.iqk.evaluation.vo.EvalComparisonVO;
import com.enterprise.iqk.evaluation.vo.EvalDatasetCreateVO;
import com.enterprise.iqk.evaluation.vo.EvalDatasetVO;
import com.enterprise.iqk.evaluation.vo.EvalMetricSummaryVO;
import com.enterprise.iqk.evaluation.vo.EvalResultVO;
import com.enterprise.iqk.evaluation.vo.EvalRunRequestVO;
import com.enterprise.iqk.evaluation.vo.EvalRunVO;
import com.enterprise.iqk.rag.HybridRagAnswerService;
import com.enterprise.iqk.retrieval.CitationItem;
import com.enterprise.iqk.retrieval.EvidenceItem;
import com.enterprise.iqk.security.TenantContext;
import com.enterprise.iqk.util.ConversationIdHelper;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

@Service
@RequiredArgsConstructor
public class EvaluationService {
    private static final double PASS_THRESHOLD = 0.70;

    private final EvalDatasetMapper evalDatasetMapper;
    private final EvalCaseMapper evalCaseMapper;
    private final EvalRunMapper evalRunMapper;
    private final EvalResultMapper evalResultMapper;
    private final HybridRagAnswerService hybridRagAnswerService;
    private final ObjectMapper objectMapper;
    private final EvaluationScorer evaluationScorer;
    private final EvaluationReportRenderer evaluationReportRenderer;

    public EvalDatasetVO createDataset(String tenantId, EvalDatasetCreateVO request) {
        if (request == null) {
            throw new IllegalArgumentException("dataset payload is required");
        }
        if (!StringUtils.hasText(request.getName())) {
            throw new IllegalArgumentException("dataset name is required");
        }
        if (request.getCases() == null || request.getCases().isEmpty()) {
            throw new IllegalArgumentException("dataset cases are required");
        }

        String tenant = TenantContext.normalize(tenantId);
        String datasetId = "eval-ds-" + shortUuid();
        LocalDateTime now = LocalDateTime.now();
        EvalDatasetRecord dataset = EvalDatasetRecord.builder()
                .datasetId(datasetId)
                .tenantId(tenant)
                .name(request.getName().trim())
                .description(emptyIfBlank(request.getDescription()))
                .createdAt(now)
                .updatedAt(now)
                .build();
        evalDatasetMapper.insert(dataset);

        int order = 0;
        for (EvalCaseCreateVO item : request.getCases()) {
            if (item == null || !StringUtils.hasText(item.getQuestion())) {
                throw new IllegalArgumentException("case question is required");
            }
            String caseId = StringUtils.hasText(item.getCaseId())
                    ? item.getCaseId().trim()
                    : "case-" + String.format(Locale.ROOT, "%03d", order + 1);
            evalCaseMapper.insert(EvalCaseRecord.builder()
                    .caseId(caseId)
                    .datasetId(datasetId)
                    .tenantId(tenant)
                    .category(emptyIfBlank(item.getCategory()))
                    .chatId(emptyIfBlank(item.getChatId()))
                    .questionText(item.getQuestion().trim())
                    .expectedCitationsJson(writeJsonList(item.getExpectedCitations()))
                    .expectedKeywordsJson(writeJsonList(item.getExpectedKeywords()))
                    .forbiddenKeywordsJson(writeJsonList(item.getForbiddenKeywords()))
                    .sortOrder(order++)
                    .createdAt(now)
                    .updatedAt(now)
                    .build());
        }
        return toDatasetVO(dataset, order);
    }

    public List<EvalDatasetVO> listDatasets(String tenantId) {
        String tenant = TenantContext.normalize(tenantId);
        return evalDatasetMapper.findByTenant(tenant).stream()
                .map(record -> toDatasetVO(record, evalCaseMapper.findByTenantAndDatasetId(tenant, record.getDatasetId()).size()))
                .toList();
    }

    public EvalRunVO triggerRun(String tenantId, String datasetId, EvalRunRequestVO request) {
        String tenant = TenantContext.normalize(tenantId);
        EvalDatasetRecord dataset = requireDataset(tenant, datasetId);
        List<EvalCaseRecord> cases = evalCaseMapper.findByTenantAndDatasetId(tenant, datasetId);
        if (cases.isEmpty()) {
            throw new IllegalArgumentException("dataset has no cases");
        }

        String runId = "eval-run-" + shortUuid();
        LocalDateTime now = LocalDateTime.now();
        String modelProfile = request == null || !StringUtils.hasText(request.getModelProfile())
                ? "balanced"
                : request.getModelProfile().trim();
        EvalRunRecord run = EvalRunRecord.builder()
                .runId(runId)
                .datasetId(dataset.getDatasetId())
                .tenantId(tenant)
                .status("RUNNING")
                .modelProfile(modelProfile)
                .totalCases(cases.size())
                .passedCases(0)
                .runScore(0.0)
                .retrievalHitRate(0.0)
                .citationCoverageRate(0.0)
                .answerFaithfulnessScore(0.0)
                .avgLatencyMs(0.0)
                .failureRate(0.0)
                .startedAt(now)
                .createdAt(now)
                .updatedAt(now)
                .build();
        evalRunMapper.insert(run);

        List<EvalResultRecord> results = new ArrayList<>();
        for (int i = 0; i < cases.size(); i++) {
            results.add(runCase(tenant, runId, dataset.getDatasetId(), cases.get(i), request, i));
        }

        EvalMetricSummaryVO summary = summarize(results);
        run.setStatus("SUCCESS");
        run.setPassedCases(summary.getPassedCases());
        run.setRunScore(summary.getRunScore());
        run.setRetrievalHitRate(summary.getRetrievalHitRate());
        run.setCitationCoverageRate(summary.getCitationCoverageRate());
        run.setAnswerFaithfulnessScore(summary.getAnswerFaithfulnessScore());
        run.setAvgLatencyMs(summary.getAvgLatencyMs());
        run.setFailureRate(summary.getFailureRate());
        run.setFinishedAt(LocalDateTime.now());
        run.setUpdatedAt(run.getFinishedAt());
        evalRunMapper.updateById(run);

        return toRunVO(run, results);
    }

    public EvalRunVO getRun(String tenantId, String runId) {
        String tenant = TenantContext.normalize(tenantId);
        EvalRunRecord run = requireRun(tenant, runId);
        return toRunVO(run, evalResultMapper.findByTenantAndRunId(tenant, runId));
    }

    public EvalRunVO markBaseline(String tenantId, String runId) {
        String tenant = TenantContext.normalize(tenantId);
        EvalRunRecord run = requireRun(tenant, runId);
        int updated = evalDatasetMapper.updateBaselineRunId(tenant, run.getDatasetId(), runId);
        if (updated <= 0) {
            throw new IllegalArgumentException("dataset not found");
        }
        return getRun(tenant, runId);
    }

    public EvalComparisonVO compareLatest(String tenantId, String datasetId) {
        String tenant = TenantContext.normalize(tenantId);
        EvalDatasetRecord dataset = requireDataset(tenant, datasetId);
        List<EvalRunRecord> recent = evalRunMapper.findRecentByDatasetId(tenant, datasetId, 2);
        EvalRunVO current = recent.isEmpty()
                ? null
                : toRunVO(recent.get(0), evalResultMapper.findByTenantAndRunId(tenant, recent.get(0).getRunId()));

        EvalRunVO baseline = null;
        if (StringUtils.hasText(dataset.getBaselineRunId())) {
            EvalRunRecord baselineRun = evalRunMapper.findByTenantAndRunId(tenant, dataset.getBaselineRunId());
            if (baselineRun != null) {
                baseline = toRunVO(baselineRun, evalResultMapper.findByTenantAndRunId(tenant, baselineRun.getRunId()));
            }
        }
        if (baseline == null && recent.size() > 1) {
            EvalRunRecord previous = recent.get(1);
            baseline = toRunVO(previous, evalResultMapper.findByTenantAndRunId(tenant, previous.getRunId()));
        }

        return EvalComparisonVO.builder()
                .dataset(toDatasetVO(dataset, evalCaseMapper.findByTenantAndDatasetId(tenant, datasetId).size()))
                .baseline(baseline)
                .current(current)
                .build();
    }

    public String exportReport(String tenantId, String runId) {
        return evaluationReportRenderer.render(getRun(tenantId, runId));
    }

    private EvalResultRecord runCase(String tenant,
                                     String runId,
                                     String datasetId,
                                     EvalCaseRecord evalCase,
                                     EvalRunRequestVO request,
                                     int index) {
        long startedNs = System.nanoTime();
        String status = "SUCCESS";
        String answer = "";
        String errorMessage = "";
        List<String> citations = List.of();
        List<String> evidence = List.of();

        try {
            String chatId = resolveChatId(evalCase, request, index);
            HybridRagAnswerService.HybridRagResult result = hybridRagAnswerService.answer(
                    evalCase.getQuestionText(),
                    tenant,
                    chatId,
                    ConversationIdHelper.build("eval", chatId),
                    request == null ? null : request.getModelProfile()
            );
            answer = emptyIfBlank(result.getAnswer());
            citations = toCitationStrings(result.getCitations());
            evidence = toEvidenceStrings(result.getEvidence());
            if (!StringUtils.hasText(answer)) {
                status = "FAILED";
                errorMessage = "empty answer";
            }
        } catch (RuntimeException ex) {
            status = "FAILED";
            errorMessage = StringUtils.hasText(ex.getMessage()) ? ex.getMessage() : "evaluation case failed";
        }

        long latencyMs = TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - startedNs);
        EvaluationScorer.CaseScores scores = evaluationScorer.scoreCase(
                evalCase,
                answer,
                citations,
                evidence,
                "FAILED".equals(status)
        );
        EvalResultRecord record = EvalResultRecord.builder()
                .resultId("eval-result-" + shortUuid())
                .runId(runId)
                .datasetId(datasetId)
                .caseId(evalCase.getCaseId())
                .tenantId(tenant)
                .status(status)
                .questionText(evalCase.getQuestionText())
                .answerText(answer)
                .citationsJson(writeJsonList(citations))
                .evidenceJson(writeJsonList(evidence))
                .retrievalHit(scores.retrievalHit())
                .citationCoverage(scores.citationCoverage())
                .keywordScore(scores.keywordScore())
                .answerFaithfulness(scores.answerFaithfulness())
                .score(scores.score())
                .latencyMs(latencyMs)
                .errorMessage(errorMessage)
                .createdAt(LocalDateTime.now())
                .build();
        evalResultMapper.insert(record);
        return record;
    }

    private EvalMetricSummaryVO summarize(List<EvalResultRecord> results) {
        int total = results.size();
        int passed = (int) results.stream()
                .filter(item -> "SUCCESS".equals(item.getStatus()))
                .filter(item -> item.getScore() != null && item.getScore() >= PASS_THRESHOLD)
                .count();
        double totalSafe = Math.max(1, total);
        return EvalMetricSummaryVO.builder()
                .totalCases(total)
                .passedCases(passed)
                .runScore(round(avg(results.stream().map(EvalResultRecord::getScore).toList())))
                .retrievalHitRate(round(avg(results.stream().map(EvalResultRecord::getRetrievalHit).toList())))
                .citationCoverageRate(round(avg(results.stream().map(EvalResultRecord::getCitationCoverage).toList())))
                .answerFaithfulnessScore(round(avg(results.stream().map(EvalResultRecord::getAnswerFaithfulness).toList())))
                .avgLatencyMs(round(avg(results.stream().map(item -> item.getLatencyMs() == null ? null : item.getLatencyMs().doubleValue()).toList())))
                .failureRate(round(results.stream().filter(item -> !"SUCCESS".equals(item.getStatus())).count() / totalSafe))
                .build();
    }

    private EvalDatasetRecord requireDataset(String tenant, String datasetId) {
        if (!StringUtils.hasText(datasetId)) {
            throw new IllegalArgumentException("dataset id is required");
        }
        EvalDatasetRecord dataset = evalDatasetMapper.findByTenantAndDatasetId(tenant, datasetId.trim());
        if (dataset == null) {
            throw new IllegalArgumentException("dataset not found");
        }
        return dataset;
    }

    private EvalRunRecord requireRun(String tenant, String runId) {
        if (!StringUtils.hasText(runId)) {
            throw new IllegalArgumentException("run id is required");
        }
        EvalRunRecord run = evalRunMapper.findByTenantAndRunId(tenant, runId.trim());
        if (run == null) {
            throw new IllegalArgumentException("run not found");
        }
        return run;
    }

    private EvalDatasetVO toDatasetVO(EvalDatasetRecord record, int caseCount) {
        return EvalDatasetVO.builder()
                .datasetId(record.getDatasetId())
                .tenantId(record.getTenantId())
                .name(record.getName())
                .description(record.getDescription())
                .baselineRunId(record.getBaselineRunId())
                .caseCount(caseCount)
                .createdAt(formatTime(record.getCreatedAt()))
                .updatedAt(formatTime(record.getUpdatedAt()))
                .build();
    }

    private EvalRunVO toRunVO(EvalRunRecord run, List<EvalResultRecord> results) {
        EvalMetricSummaryVO metrics = EvalMetricSummaryVO.builder()
                .totalCases(intOrZero(run.getTotalCases()))
                .passedCases(intOrZero(run.getPassedCases()))
                .runScore(valueOrZero(run.getRunScore()))
                .retrievalHitRate(valueOrZero(run.getRetrievalHitRate()))
                .citationCoverageRate(valueOrZero(run.getCitationCoverageRate()))
                .answerFaithfulnessScore(valueOrZero(run.getAnswerFaithfulnessScore()))
                .avgLatencyMs(valueOrZero(run.getAvgLatencyMs()))
                .failureRate(valueOrZero(run.getFailureRate()))
                .build();
        return EvalRunVO.builder()
                .runId(run.getRunId())
                .datasetId(run.getDatasetId())
                .tenantId(run.getTenantId())
                .status(run.getStatus())
                .modelProfile(run.getModelProfile())
                .metrics(metrics)
                .results(results == null ? List.of() : results.stream().map(this::toResultVO).toList())
                .errorMessage(run.getErrorMessage())
                .startedAt(formatTime(run.getStartedAt()))
                .finishedAt(formatTime(run.getFinishedAt()))
                .createdAt(formatTime(run.getCreatedAt()))
                .build();
    }

    private EvalResultVO toResultVO(EvalResultRecord record) {
        return EvalResultVO.builder()
                .resultId(record.getResultId())
                .caseId(record.getCaseId())
                .status(record.getStatus())
                .question(record.getQuestionText())
                .answer(record.getAnswerText())
                .citations(readJsonList(record.getCitationsJson()))
                .evidence(readJsonList(record.getEvidenceJson()))
                .retrievalHit(valueOrZero(record.getRetrievalHit()))
                .citationCoverage(valueOrZero(record.getCitationCoverage()))
                .keywordScore(valueOrZero(record.getKeywordScore()))
                .answerFaithfulness(valueOrZero(record.getAnswerFaithfulness()))
                .score(valueOrZero(record.getScore()))
                .latencyMs(record.getLatencyMs() == null ? 0 : record.getLatencyMs())
                .errorMessage(record.getErrorMessage())
                .build();
    }

    private String resolveChatId(EvalCaseRecord evalCase, EvalRunRequestVO request, int index) {
        if (StringUtils.hasText(evalCase.getChatId())) {
            return evalCase.getChatId().trim();
        }
        if (request != null && StringUtils.hasText(request.getChatIdPrefix())) {
            return request.getChatIdPrefix().trim() + "-" + String.format(Locale.ROOT, "%03d", index + 1);
        }
        return evalCase.getDatasetId();
    }

    private List<String> toCitationStrings(List<CitationItem> items) {
        if (items == null || items.isEmpty()) {
            return List.of();
        }
        Set<String> values = new LinkedHashSet<>();
        for (CitationItem item : items) {
            if (item == null) {
                continue;
            }
            String text = "%s:%s:%s".formatted(
                    emptyIfBlank(item.getSourceType()),
                    emptyIfBlank(item.getTitle()),
                    emptyIfBlank(item.getChunkId())
            );
            if (StringUtils.hasText(text.replace(":", ""))) {
                values.add(text);
            }
        }
        return List.copyOf(values);
    }

    private List<String> toEvidenceStrings(List<EvidenceItem> items) {
        if (items == null || items.isEmpty()) {
            return List.of();
        }
        List<String> values = new ArrayList<>();
        for (EvidenceItem item : items) {
            if (item != null && StringUtils.hasText(item.getSnippet())) {
                values.add(item.getSnippet());
            }
        }
        return values;
    }

    private double avg(List<Double> values) {
        if (values == null || values.isEmpty()) {
            return 0.0;
        }
        double sum = 0.0;
        int count = 0;
        for (Double value : values) {
            if (value == null) {
                continue;
            }
            sum += value;
            count++;
        }
        return count == 0 ? 0.0 : sum / count;
    }

    private String writeJsonList(List<String> values) {
        try {
            return objectMapper.writeValueAsString(values == null ? List.of() : values);
        } catch (JsonProcessingException ex) {
            return "[]";
        }
    }

    private List<String> readJsonList(String json) {
        if (!StringUtils.hasText(json)) {
            return List.of();
        }
        try {
            return objectMapper.readValue(json, new TypeReference<List<String>>() {
            });
        } catch (JsonProcessingException ex) {
            return List.of();
        }
    }

    private double valueOrZero(Double value) {
        return value == null ? 0.0 : value;
    }

    private int intOrZero(Integer value) {
        return value == null ? 0 : value;
    }

    private double round(double value) {
        return Math.round(value * 10000.0) / 10000.0;
    }

    private String formatTime(LocalDateTime value) {
        return value == null ? "" : value.format(DateTimeFormatter.ISO_LOCAL_DATE_TIME);
    }

    private String shortUuid() {
        return UUID.randomUUID().toString().replace("-", "").substring(0, 12);
    }

    private String emptyIfBlank(String value) {
        return StringUtils.hasText(value) ? value : "";
    }
}
