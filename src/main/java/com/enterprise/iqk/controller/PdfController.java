package com.enterprise.iqk.controller;

import com.enterprise.iqk.domain.IngestionJob;
import com.enterprise.iqk.domain.vo.IngestionJobVO;
import com.enterprise.iqk.domain.vo.IngestionSubmitVO;
import com.enterprise.iqk.config.properties.IngestionProperties;
import com.enterprise.iqk.ingestion.IngestionService;
import com.enterprise.iqk.rag.RagAnswerService;
import com.enterprise.iqk.repository.ChatHistoryRepository;
import com.enterprise.iqk.util.ConversationIdHelper;
import lombok.RequiredArgsConstructor;
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.util.StringUtils;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Flux;

import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.List;

import static org.springframework.http.HttpStatus.NOT_FOUND;

@RequiredArgsConstructor
@RestController
@RequestMapping("/ai/pdf")
public class PdfController {

    private final IngestionService ingestionService;
    private final ChatHistoryRepository chatHistoryRepository;
    private final RagAnswerService ragAnswerService;
    private final IngestionProperties ingestionProperties;

    @RequestMapping("/upload/{chatId}")
    public IngestionSubmitVO uploadPdf(@PathVariable String chatId,
                                       @RequestParam("file") MultipartFile file,
                                       @RequestHeader(value = "X-Idempotency-Key", required = false) String idempotencyKey) {
        IngestionJob job = ingestionService.submitPdf(chatId, file, idempotencyKey, "");
        chatHistoryRepository.save("pdf", chatId);
        return IngestionSubmitVO.builder()
                .ok(1)
                .msg("accepted")
                .job(IngestionJobVO.builder()
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
                        .build())
                .build();
    }

    @GetMapping("/file/{chatId}")
    public ResponseEntity<Resource> download(@PathVariable("chatId") String chatId) {
        List<IngestionJob> jobs = ingestionService.listByChatId(chatId, 1);
        if (jobs.isEmpty()) {
            throw new ResponseStatusException(NOT_FOUND, "file not found");
        }
        IngestionJob latest = jobs.get(0);
        Resource resource = new FileSystemResource(latest.getFilePath());
        if (!resource.exists()) {
            throw new ResponseStatusException(NOT_FOUND, "file not found");
        }
        String filename = URLEncoder.encode(
                resource.getFilename() == null ? "document.pdf" : resource.getFilename(),
                StandardCharsets.UTF_8
        );
        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_OCTET_STREAM)
                .header("Content-Disposition", "attachment; filename=\"" + filename + "\"")
                .body(resource);
    }

    @RequestMapping(value = "/chat", produces = "text/html;charset=UTF-8")
    public Flux<String> chat(@RequestParam("prompt") String prompt,
                             @RequestParam("chatId") String chatId,
                             @RequestParam(value = "modelProfile", required = false) String modelProfile) {
        chatHistoryRepository.save("pdf", chatId);
        String conversationId = ConversationIdHelper.build("pdf", chatId);
        RagAnswerService.RagResult result = ragAnswerService.answer(prompt, sanitize(chatId), conversationId, modelProfile);
        StringBuilder output = new StringBuilder(result.getAnswer());
        if (result.getCitations() != null && !result.getCitations().isEmpty()) {
            output.append("\n\n引用来源:\n");
            for (int i = 0; i < result.getCitations().size(); i++) {
                output.append("[").append(i + 1).append("] ").append(result.getCitations().get(i)).append("\n");
            }
        }
        return Flux.just(output.toString());
    }

    private String sanitize(String value) {
        if (!StringUtils.hasText(value)) {
            return "";
        }
        return value.replace("'", "");
    }
}
