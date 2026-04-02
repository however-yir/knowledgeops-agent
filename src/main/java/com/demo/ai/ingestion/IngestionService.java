package com.demo.ai.ingestion;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.demo.ai.config.properties.IngestionProperties;
import com.demo.ai.config.properties.RagProperties;
import com.demo.ai.config.properties.VectorStoreProperties;
import com.demo.ai.domain.IngestionJob;
import com.demo.ai.domain.enums.IngestionJobStatus;
import com.demo.ai.ingestion.queue.IngestionQueue;
import com.demo.ai.mapper.IngestionJobMapper;
import com.demo.ai.security.FileSafetyScanner;
import com.demo.ai.util.HashUtils;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.ai.document.Document;
import org.springframework.ai.reader.ExtractedTextFormatter;
import org.springframework.ai.reader.pdf.PagePdfDocumentReader;
import org.springframework.ai.reader.pdf.config.PdfDocumentReaderConfig;
import org.springframework.ai.transformer.splitter.TokenTextSplitter;
import org.springframework.ai.vectorstore.SimpleVectorStore;
import org.springframework.ai.vectorstore.VectorStore;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.core.io.FileSystemResource;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;
import org.springframework.web.multipart.MultipartFile;

import java.io.File;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.LocalDateTime;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

@Slf4j
@Service
@RequiredArgsConstructor
public class IngestionService {

    private final IngestionJobMapper ingestionJobMapper;
    private final VectorStore vectorStore;
    private final IngestionProperties ingestionProperties;
    private final VectorStoreProperties vectorStoreProperties;
    private final RagProperties ragProperties;
    private final MeterRegistry meterRegistry;
    private final IngestionQueue ingestionQueue;
    private final FileSafetyScanner fileSafetyScanner;

    public IngestionJob submitPdf(String chatId, MultipartFile file, String idempotencyKey, String traceId) {
        if (!StringUtils.hasText(chatId)) {
            throw new IllegalArgumentException("chatId is required");
        }
        if (file == null || file.isEmpty()) {
            throw new IllegalArgumentException("file is required");
        }
        fileSafetyScanner.scan(file);

        String sourceName = StringUtils.hasText(file.getOriginalFilename()) ? file.getOriginalFilename() : "unknown.pdf";
        String normalizedKey = normalizeIdempotencyKey(chatId, file, idempotencyKey);
        IngestionJob existing = ingestionJobMapper.findByIdempotencyKey(normalizedKey);
        if (existing != null) {
            return existing;
        }

        String jobId = "job-" + UUID.randomUUID();
        LocalDateTime now = LocalDateTime.now();
        String filePath = persistFile(jobId, sourceName, file);
        IngestionJob job = IngestionJob.builder()
                .jobId(jobId)
                .chatId(chatId)
                .sourceType("PDF")
                .sourceName(sourceName)
                .filePath(filePath)
                .idempotencyKey(normalizedKey)
                .status(IngestionJobStatus.PENDING)
                .traceId(traceId)
                .attemptCount(0)
                .maxRetries(ingestionProperties.getMaxRetries())
                .createdAt(now)
                .updatedAt(now)
                .build();
        try {
            ingestionJobMapper.insert(job);
            if (!"db_polling".equalsIgnoreCase(ingestionProperties.getQueueBackend())) {
                ingestionQueue.publishJob(job.getJobId(), traceId);
            }
            Counter.builder("ingestion.jobs.submitted")
                    .tag("source", "pdf")
                    .register(meterRegistry)
                    .increment();
            return job;
        } catch (DuplicateKeyException duplicateKeyException) {
            IngestionJob concurrent = ingestionJobMapper.findByIdempotencyKey(normalizedKey);
            if (concurrent != null) {
                return concurrent;
            }
            throw duplicateKeyException;
        }
    }

    public IngestionJob getByJobId(String jobId) {
        return ingestionJobMapper.findByJobId(jobId);
    }

    public List<IngestionJob> listByChatId(String chatId, int limit) {
        return ingestionJobMapper.findLatestByChatId(chatId, Math.max(limit, 1));
    }

    public IngestionProcessResult processQueuedJob(String jobId, String traceId) {
        if (!StringUtils.hasText(jobId)) {
            return IngestionProcessResult.builder()
                    .picked(false)
                    .status(IngestionJobStatus.FAILED)
                    .jobId("")
                    .traceId(traceId)
                    .errorMessage("jobId missing")
                    .build();
        }
        LocalDateTime now = LocalDateTime.now();
        int claimed = ingestionJobMapper.claimForRun(jobId, IngestionJobStatus.RUNNING, now, now);
        if (claimed == 0) {
            return IngestionProcessResult.builder()
                    .picked(false)
                    .status(IngestionJobStatus.RUNNING)
                    .jobId(jobId)
                    .traceId(traceId)
                    .build();
        }

        IngestionJob running = getByJobId(jobId);
        if (running == null) {
            return IngestionProcessResult.builder()
                    .picked(false)
                    .status(IngestionJobStatus.FAILED)
                    .jobId(jobId)
                    .traceId(traceId)
                    .errorMessage("job not found after claim")
                    .build();
        }

        Timer.Sample sample = Timer.start(meterRegistry);
        try {
            processPdfJob(running);
            ingestionJobMapper.updateTerminalState(
                    running.getJobId(),
                    IngestionJobStatus.SUCCEEDED,
                    LocalDateTime.now(),
                    LocalDateTime.now(),
                    null,
                    null
            );
            sample.stop(Timer.builder("ingestion.jobs.duration")
                    .tag("status", "succeeded")
                    .register(meterRegistry));
            Counter.builder("ingestion.jobs.finished")
                    .tag("status", "succeeded")
                    .register(meterRegistry)
                    .increment();
            return IngestionProcessResult.builder()
                    .picked(true)
                    .status(IngestionJobStatus.SUCCEEDED)
                    .jobId(running.getJobId())
                    .traceId(traceId)
                    .build();
        } catch (Exception ex) {
            log.error("Failed to process ingestion job: {}", running.getJobId(), ex);
            IngestionJob latest = getByJobId(running.getJobId());
            int attempts = latest != null && latest.getAttemptCount() != null ? latest.getAttemptCount() : 1;
            int maxRetries = latest != null && latest.getMaxRetries() != null ? latest.getMaxRetries() : ingestionProperties.getMaxRetries();

            IngestionJobStatus nextStatus = attempts < maxRetries ? IngestionJobStatus.RETRY : IngestionJobStatus.FAILED;
            LocalDateTime nextRetryAt = null;
            if (nextStatus == IngestionJobStatus.RETRY) {
                int delaySeconds = ingestionProperties.getBaseDelaySeconds() * Math.max(1, attempts);
                nextRetryAt = LocalDateTime.now().plusSeconds(delaySeconds);
            }
            String error = truncateError(ex.getMessage());
            ingestionJobMapper.updateTerminalState(
                    running.getJobId(),
                    nextStatus,
                    LocalDateTime.now(),
                    LocalDateTime.now(),
                    error,
                    nextRetryAt
            );
            sample.stop(Timer.builder("ingestion.jobs.duration")
                    .tag("status", nextStatus.name().toLowerCase())
                    .register(meterRegistry));
            Counter.builder("ingestion.jobs.finished")
                    .tag("status", nextStatus.name().toLowerCase())
                    .register(meterRegistry)
                    .increment();

            if (nextStatus == IngestionJobStatus.FAILED) {
                ingestionQueue.publishDlq(running.getJobId(), traceId, error);
            }
            return IngestionProcessResult.builder()
                    .picked(true)
                    .status(nextStatus)
                    .jobId(running.getJobId())
                    .traceId(traceId)
                    .errorMessage(error)
                    .build();
        }
    }

    public int enqueueReadyRetries(int limit) {
        if ("db_polling".equalsIgnoreCase(ingestionProperties.getQueueBackend())) {
            return 0;
        }
        List<IngestionJob> ready = ingestionJobMapper.findReadyRetries(LocalDateTime.now(), Math.max(1, limit));
        int count = 0;
        for (IngestionJob job : ready) {
            int updated = ingestionJobMapper.requeueRetry(job.getJobId(), LocalDateTime.now());
            if (updated > 0) {
                ingestionQueue.publishJob(job.getJobId(), job.getTraceId());
                count++;
            }
        }
        return count;
    }

    private void processPdfJob(IngestionJob job) {
        File source = new File(job.getFilePath());
        if (!source.exists()) {
            throw new IllegalStateException("PDF file missing: " + job.getFilePath());
        }
        PagePdfDocumentReader reader = new PagePdfDocumentReader(
                new FileSystemResource(source),
                PdfDocumentReaderConfig.builder()
                        .withPageExtractedTextFormatter(ExtractedTextFormatter.defaults())
                        .withPagesPerDocument(1)
                        .build()
        );
        List<Document> pages = reader.read();
        List<Document> chunks = splitDocuments(pages, job);
        vectorStore.add(chunks);
        persistSimpleVectorStoreIfNeeded();
    }

    private List<Document> splitDocuments(List<Document> pages, IngestionJob job) {
        TokenTextSplitter splitter = new TokenTextSplitter(
                ragProperties.getSplit().getChunkSize(),
                ragProperties.getSplit().getMinChunkSize(),
                5,
                ragProperties.getSplit().getMaxNumChunks(),
                true
        );
        List<Document> chunks = splitter.apply(pages);
        for (int i = 0; i < chunks.size(); i++) {
            Document chunk = chunks.get(i);
            Map<String, Object> metadata = new HashMap<>(chunk.getMetadata());
            metadata.put("chat_id", job.getChatId());
            metadata.put("job_id", job.getJobId());
            metadata.put("file_name", job.getSourceName());
            metadata.put("source_type", job.getSourceType());
            metadata.put("chunk_index", i);
            chunk.getMetadata().clear();
            chunk.getMetadata().putAll(metadata);
        }
        return chunks;
    }

    private void persistSimpleVectorStoreIfNeeded() {
        if (!(vectorStore instanceof SimpleVectorStore simpleVectorStore)) {
            return;
        }
        if (!"simple".equalsIgnoreCase(vectorStoreProperties.getBackend())) {
            return;
        }
        String storePath = vectorStoreProperties.getSimpleStorePath();
        try {
            Path path = Path.of(storePath);
            if (path.getParent() != null) {
                Files.createDirectories(path.getParent());
            }
            simpleVectorStore.save(path.toFile());
        } catch (Exception e) {
            log.warn("Failed to persist SimpleVectorStore snapshot", e);
        }
    }

    private String persistFile(String jobId, String sourceName, MultipartFile file) {
        String sanitized = sourceName.replaceAll("[^a-zA-Z0-9._-]", "_");
        Path root = Path.of(ingestionProperties.getStorageDir());
        Path target = root.resolve(jobId + "_" + sanitized);
        try {
            Files.createDirectories(root);
            file.transferTo(target);
            return target.toAbsolutePath().toString();
        } catch (IOException e) {
            throw new IllegalStateException("Failed to store uploaded PDF", e);
        }
    }

    private String normalizeIdempotencyKey(String chatId, MultipartFile file, String provided) {
        if (StringUtils.hasText(provided)) {
            return "client:" + provided.trim();
        }
        String seed = chatId + "|" + file.getOriginalFilename() + "|" + file.getSize();
        return "auto:" + HashUtils.sha256Hex(seed);
    }

    private String truncateError(String msg) {
        if (!StringUtils.hasText(msg)) {
            return "unknown error";
        }
        return msg.length() <= 1000 ? msg : msg.substring(0, 1000);
    }
}
