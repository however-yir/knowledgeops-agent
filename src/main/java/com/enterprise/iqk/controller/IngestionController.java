package com.enterprise.iqk.controller;

import com.enterprise.iqk.domain.IngestionJob;
import com.enterprise.iqk.domain.vo.IngestionJobVO;
import com.enterprise.iqk.domain.vo.IngestionSubmitVO;
import com.enterprise.iqk.config.properties.IngestionProperties;
import com.enterprise.iqk.ingestion.IngestionProcessResult;
import com.enterprise.iqk.ingestion.IngestionService;
import com.enterprise.iqk.repository.ChatHistoryRepository;
import io.micrometer.tracing.Tracer;
import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.util.StringUtils;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;

import java.util.List;

@RestController
@RequestMapping("/ingestion")
@RequiredArgsConstructor
public class IngestionController {

    private final IngestionService ingestionService;
    private final ChatHistoryRepository chatHistoryRepository;
    private final ObjectProvider<Tracer> tracerProvider;
    private final IngestionProperties ingestionProperties;

    @PostMapping("/upload/{chatId}")
    public IngestionSubmitVO uploadPdf(@PathVariable String chatId,
                                       @RequestParam("file") MultipartFile file,
                                       @RequestHeader(value = "X-Idempotency-Key", required = false) String idempotencyKey) {
        String traceId = currentTraceId();
        IngestionJob job = ingestionService.submitPdf(chatId, file, idempotencyKey, traceId);
        chatHistoryRepository.save("pdf", chatId);
        return IngestionSubmitVO.builder()
                .ok(1)
                .msg("accepted")
                .job(toVO(job))
                .build();
    }

    @GetMapping("/jobs/{jobId}")
    public IngestionJobVO getJob(@PathVariable String jobId) {
        IngestionJob job = ingestionService.getByJobId(jobId);
        if (job == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "job not found");
        }
        return toVO(job);
    }

    @GetMapping("/jobs")
    public List<IngestionJobVO> getJobsByChatId(@RequestParam("chatId") String chatId,
                                                @RequestParam(value = "limit", defaultValue = "20") int limit) {
        return ingestionService.listByChatId(chatId, Math.max(1, Math.min(limit, 100)))
                .stream()
                .map(this::toVO)
                .toList();
    }

    @PostMapping("/jobs/process")
    @PreAuthorize("hasRole('ADMIN')")
    public IngestionSubmitVO processOne(@RequestParam(value = "jobId", required = false) String jobId) {
        if (!StringUtils.hasText(jobId)) {
            int enqueued = ingestionService.enqueueReadyRetries(20);
            return IngestionSubmitVO.builder()
                    .ok(1)
                    .msg("requeue=" + enqueued)
                    .job(null)
                    .build();
        }
        IngestionProcessResult processed = ingestionService.processQueuedJob(jobId, currentTraceId());
        boolean picked = processed.isPicked();
        return IngestionSubmitVO.builder()
                .ok(1)
                .msg(picked ? "processed" : "empty")
                .job(null)
                .build();
    }

    private IngestionJobVO toVO(IngestionJob job) {
        return IngestionJobVO.builder()
                .jobId(job.getJobId())
                .chatId(job.getChatId())
                .sourceName(job.getSourceName())
                .status(job.getStatus())
                .attemptCount(job.getAttemptCount())
                .maxRetries(job.getMaxRetries())
                .errorMessage(job.getErrorMessage())
                .traceId(job.getTraceId())
                .queueBackend(ingestionProperties.getQueueBackend())
                .createdAt(job.getCreatedAt())
                .startedAt(job.getStartedAt())
                .finishedAt(job.getFinishedAt())
                .build();
    }

    private String currentTraceId() {
        Tracer tracer = tracerProvider.getIfAvailable();
        if (tracer == null || tracer.currentSpan() == null) {
            return "";
        }
        String traceId = tracer.currentSpan().context().traceId();
        return StringUtils.hasText(traceId) ? traceId : "";
    }
}
