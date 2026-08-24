package com.enterprise.iqk.controller;

import com.enterprise.iqk.config.properties.IngestionProperties;
import com.enterprise.iqk.domain.IngestionJob;
import com.enterprise.iqk.domain.enums.IngestionJobStatus;
import com.enterprise.iqk.ingestion.IngestionService;
import com.enterprise.iqk.rag.RagAnswerService;
import com.enterprise.iqk.repository.ChatHistoryRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.FilterType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MockMvc;

import java.time.LocalDateTime;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(value = PdfController.class, excludeFilters = {
        @ComponentScan.Filter(
                type = FilterType.ASSIGNABLE_TYPE,
                classes = com.enterprise.iqk.security.ApiKeyOrJwtAuthFilter.class
        ),
        @ComponentScan.Filter(
                type = FilterType.ASSIGNABLE_TYPE,
                classes = com.enterprise.iqk.security.RateLimitFilter.class
        ),
        @ComponentScan.Filter(
                type = FilterType.ASSIGNABLE_TYPE,
                classes = com.enterprise.iqk.security.AuditLogFilter.class
        ),
        @ComponentScan.Filter(
                type = FilterType.ASSIGNABLE_TYPE,
                classes = com.enterprise.iqk.security.HttpMetricsFilter.class
        ),
        @ComponentScan.Filter(
                type = FilterType.ASSIGNABLE_TYPE,
                classes = com.enterprise.iqk.security.RequestContextFilter.class
        )
})
@AutoConfigureMockMvc(addFilters = false)
class PdfControllerWebMvcTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private IngestionService ingestionService;

    @MockBean
    private ChatHistoryRepository chatHistoryRepository;

    @MockBean
    private RagAnswerService ragAnswerService;

    @MockBean
    private IngestionProperties ingestionProperties;

    @Test
    //请求不带file  返回400 提示文件不为空
    void shouldRejectMissingFile() throws Exception {
        mockMvc.perform(
                        multipart("/ai/pdf/upload/chat-1")
                )
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.msg")
                        .value("上传文件不能为空"));

        verifyNoInteractions(ingestionService);
    }

    @Test
    //上传0字节文件      400提示文件不能为空
    void shouldRejectEmptyFile() throws Exception {
        MockMultipartFile file = new MockMultipartFile(
                "file",
                "empty.pdf",
                "application/pdf",
                new byte[0]
        );

        mockMvc.perform(
                        multipart("/ai/pdf/upload/chat-1")
                                .file(file)
                )
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.msg")
                        .value("上传文件不能为空"));

        verifyNoInteractions(ingestionService);
    }

    @Test
    //上传 .txt文件，   400 只允许pdf
    void shouldRejectNonPdfFile() throws Exception {
        MockMultipartFile file = new MockMultipartFile(
                "file",
                "document.txt",
                "text/plain",
                "plain text".getBytes()
        );

        mockMvc.perform(
                        multipart("/ai/pdf/upload/chat-1")
                                .file(file)
                )
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.msg")
                        .value("只允许上传PDF文件"));

        verifyNoInteractions(ingestionService);
    }

    @Test
    //文件名是.pdf    400只允许pdf
    void shouldRejectPdfExtensionWithWrongContentType() throws Exception {
        MockMultipartFile file = new MockMultipartFile(
                "file",
                "document.pdf",
                "text/plain",
                "plain text".getBytes()
        );

        mockMvc.perform(
                        multipart("/ai/pdf/upload/chat-1")
                                .file(file)
                )
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.msg")
                        .value("只允许上传PDF文件"));

        verifyNoInteractions(ingestionService);
    }

    @Test
    // 合法PDF   200
    void shouldAcceptPdfFile() throws Exception {
        MockMultipartFile file = new MockMultipartFile(
                "file",
                "document.pdf",
                "application/pdf",
                "%PDF-1.7\ncontent".getBytes()
        );

        when(ingestionProperties.getQueueBackend())
                .thenReturn("db_polling");

        when(ingestionService.submitPdf(
                any(),
                any(),
                any(),
                any(),
                any()
        )).thenReturn(
                IngestionJob.builder()
                        .jobId("job-1")
                        .chatId("chat-1")
                        .sourceName("document.pdf")
                        .status(IngestionJobStatus.PENDING)
                        .attemptCount(0)
                        .maxRetries(3)
                        .createdAt(LocalDateTime.now())
                        .build()
        );

        mockMvc.perform(
                        multipart("/ai/pdf/upload/chat-1")
                                .file(file)
                )
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.ok").value(1))
                .andExpect(jsonPath("$.msg").value("accepted"))
                .andExpect(jsonPath("$.job.jobId").value("job-1"))
                .andExpect(jsonPath("$.job.sourceName")
                        .value("document.pdf"));

        verify(ingestionService).submitPdf(
                any(),
                any(),
                any(),
                any(),
                any()
        );
    }
}
