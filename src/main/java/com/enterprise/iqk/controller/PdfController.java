package com.enterprise.iqk.controller;

import com.enterprise.iqk.domain.IngestionJob;
import com.enterprise.iqk.domain.vo.IngestionJobVO;
import com.enterprise.iqk.domain.vo.IngestionSubmitVO;
import com.enterprise.iqk.config.properties.IngestionProperties;
import com.enterprise.iqk.ingestion.IngestionService;
import com.enterprise.iqk.rag.RagAnswerService;
import com.enterprise.iqk.repository.ChatHistoryRepository;
import com.enterprise.iqk.security.TenantContext;
import com.enterprise.iqk.util.ConversationIdHelper;
import lombok.RequiredArgsConstructor;
import org.slf4j.MDC;
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.util.StringUtils;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
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
import java.util.Locale;



import static org.springframework.http.HttpStatus.NOT_FOUND;

/**
 * PDF 知识库接口：上传并入库 PDF、下载原文件、根据 PDF 内容进行 RAG 问答。
 */
@RequiredArgsConstructor
@RestController
@RequestMapping("/ai/pdf")
public class PdfController {

    /**
     * 创建和查询 PDF 异步入库任务。
     */
    private final IngestionService ingestionService;
    /**
     * 保存 PDF 类型的会话索引。
     */
    private final ChatHistoryRepository chatHistoryRepository;
    /**
     * 检索 PDF 片段并生成答案。
     */
    private final RagAnswerService ragAnswerService;
    /**
     * 提供当前使用的入库队列配置。
     */
    private final IngestionProperties ingestionProperties;

    /**
     * 上传 PDF，并提交异步解析、切片和向量化任务。
     */
    @PostMapping(
            value = "/upload/{chatId}",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE
    )
    public IngestionSubmitVO uploadPdf(
            @PathVariable String chatId,
            @RequestParam(value = "file", required = false) MultipartFile file,
            @RequestHeader(value = "X-Idempotency-Key",
                    required = false) String idempotencyKey) {

        //新增入口检验
        if(file == null || file.isEmpty()){
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "上传文件不能为空"
            );
        }

        String filename = file.getOriginalFilename();
        String contentType = file.getContentType();

        //将文件名统一转换为小写后，再判断是否是.pdf结尾
        boolean pdfByName = StringUtils.hasText(filename)
                && filename.toLowerCase(Locale.ROOT).endsWith(".pdf");

        boolean pdfByContentType = MediaType.APPLICATION_PDF_VALUE.equalsIgnoreCase(contentType);

        if (!pdfByName || !pdfByContentType){
            throw  new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "只允许上传PDF文件"
            );
        }


        // 租户 ID 用于隔离不同企业的文件和任务。
        String tenantId = currentTenantId();
        // 这里只提交任务，不等待 PDF 全部处理完成。
        IngestionJob job = ingestionService.submitPdf(
                tenantId,
                chatId,
                file,
                idempotencyKey,
                "");
        chatHistoryRepository.save("pdf", chatId);
        // 将任务状态包装成前端需要的返回对象。
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

    /**
     * 下载该会话最近一次上传的 PDF 原文件。
     */
    @GetMapping("/file/{chatId}")
    public ResponseEntity<Resource> download(@PathVariable("chatId") String chatId) {
        // limit=1 表示只查询最近的一条上传任务。
        List<IngestionJob> jobs = ingestionService.listByChatId(currentTenantId(), chatId, 1);
        if (jobs.isEmpty()) {
            throw new ResponseStatusException(NOT_FOUND, "file not found");
        }
        IngestionJob latest = jobs.get(0);
        Resource resource = new FileSystemResource(latest.getFilePath());
        if (!resource.exists()) {
            throw new ResponseStatusException(NOT_FOUND, "file not found");
        }
        // 编码文件名，避免中文或特殊字符破坏下载响应头。
        String filename = URLEncoder.encode(
                resource.getFilename() == null ? "document.pdf" : resource.getFilename(),
                StandardCharsets.UTF_8
        );
        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_OCTET_STREAM)
                .header("Content-Disposition", "attachment; filename=\"" + filename + "\"")
                .body(resource);
    }

    /**
     * 根据已入库的 PDF 内容回答问题，并返回引用来源。
     */
    @RequestMapping(value = "/chat", produces = "text/html;charset=UTF-8")
    public Flux<String> chat(@RequestParam("prompt") String prompt,
                             @RequestParam("chatId") String chatId,
                             @RequestParam(value = "modelProfile", required = false) String modelProfile) {
        String tenantId = currentTenantId();
        chatHistoryRepository.save("pdf", chatId);
        // 使用 pdf 类型生成独立记忆键，避免与普通聊天串上下文。
        String conversationId = ConversationIdHelper.build("pdf", chatId);
        // RAG：先检索与问题相关的 PDF 片段，再让模型基于片段回答。
        RagAnswerService.RagResult result = ragAnswerService.answer(
                prompt,
                tenantId,
                sanitize(chatId),
                conversationId,
                modelProfile
        );
        // 把答案和引用来源拼接成前端可直接展示的文本。
        StringBuilder output = new StringBuilder(result.getAnswer());
        if (result.getCitations() != null && !result.getCitations().isEmpty()) {
            output.append("\n\n引用来源:\n");
            for (int i = 0; i < result.getCitations().size(); i++) {
                output.append("[").append(i + 1).append("] ").append(result.getCitations().get(i)).append("\n");
            }
        }
        // Service 当前同步生成完整答案，因此这里返回的是只有一个元素的 Flux。
        return Flux.just(output.toString());
    }

    /**
     * 去除单引号，避免 chatId 破坏向量检索的过滤表达式。
     */
    private String sanitize(String value) {
        if (!StringUtils.hasText(value)) {
            return "";
        }
        return value.replace("'", "");
    }

    /**
     * 获取当前请求所属租户，缺失时使用 public。
     */
    private String currentTenantId() {
        return TenantContext.normalize(MDC.get(TenantContext.TENANT_REQUEST_ATTRIBUTE));
    }
}
