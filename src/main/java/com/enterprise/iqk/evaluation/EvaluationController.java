package com.enterprise.iqk.evaluation;

import com.enterprise.iqk.evaluation.vo.EvalComparisonVO;
import com.enterprise.iqk.evaluation.vo.EvalDatasetCreateVO;
import com.enterprise.iqk.evaluation.vo.EvalDatasetVO;
import com.enterprise.iqk.evaluation.vo.EvalRunRequestVO;
import com.enterprise.iqk.evaluation.vo.EvalRunVO;
import com.enterprise.iqk.security.TenantContext;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/ai/evaluation")
@RequiredArgsConstructor
public class EvaluationController {
    private final EvaluationService evaluationService;

    @PostMapping("/datasets")
    public EvalDatasetVO createDataset(@RequestBody EvalDatasetCreateVO request) {
        return evaluationService.createDataset(TenantContext.currentTenantId(), request);
    }

    @GetMapping("/datasets")
    public List<EvalDatasetVO> listDatasets() {
        return evaluationService.listDatasets(TenantContext.currentTenantId());
    }

    @PostMapping("/datasets/{datasetId}/runs")
    public EvalRunVO triggerRun(@PathVariable("datasetId") String datasetId,
                                @RequestBody(required = false) EvalRunRequestVO request) {
        return evaluationService.triggerRun(TenantContext.currentTenantId(), datasetId, request);
    }

    @PostMapping("/runs")
    public EvalRunVO triggerRunByContract(@RequestBody EvalRunRequestVO request) {
        if (request == null || !org.springframework.util.StringUtils.hasText(request.getDatasetId())) {
            throw new IllegalArgumentException("datasetId is required");
        }
        return evaluationService.triggerRun(TenantContext.currentTenantId(), request.getDatasetId(), request);
    }

    @GetMapping("/datasets/{datasetId}/comparison")
    public EvalComparisonVO compareLatest(@PathVariable("datasetId") String datasetId) {
        return evaluationService.compareLatest(TenantContext.currentTenantId(), datasetId);
    }

    @GetMapping("/runs/{runId}")
    public EvalRunVO getRun(@PathVariable("runId") String runId) {
        return evaluationService.getRun(TenantContext.currentTenantId(), runId);
    }

    @PostMapping("/runs/{runId}/baseline")
    public EvalRunVO markBaseline(@PathVariable("runId") String runId) {
        return evaluationService.markBaseline(TenantContext.currentTenantId(), runId);
    }

    @GetMapping(value = "/runs/{runId}/report", produces = "text/markdown;charset=UTF-8")
    public ResponseEntity<String> exportReport(@PathVariable("runId") String runId) {
        String report = evaluationService.exportReport(TenantContext.currentTenantId(), runId);
        return ResponseEntity.ok()
                .contentType(MediaType.valueOf("text/markdown;charset=UTF-8"))
                .header(HttpHeaders.CONTENT_DISPOSITION, "attachment; filename=\"rag-evaluation-" + runId + ".md\"")
                .body(report);
    }
}
