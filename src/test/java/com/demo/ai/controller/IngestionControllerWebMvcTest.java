package com.demo.ai.controller;

import com.demo.ai.config.properties.IngestionProperties;
import com.demo.ai.domain.IngestionJob;
import com.demo.ai.domain.enums.IngestionJobStatus;
import com.demo.ai.ingestion.IngestionService;
import com.demo.ai.repository.ChatHistoryRepository;
import io.micrometer.tracing.Tracer;
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
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(value = IngestionController.class, excludeFilters = {
        @ComponentScan.Filter(type = FilterType.ASSIGNABLE_TYPE, classes = com.demo.ai.security.ApiKeyOrJwtAuthFilter.class),
        @ComponentScan.Filter(type = FilterType.ASSIGNABLE_TYPE, classes = com.demo.ai.security.RateLimitFilter.class),
        @ComponentScan.Filter(type = FilterType.ASSIGNABLE_TYPE, classes = com.demo.ai.security.AuditLogFilter.class),
        @ComponentScan.Filter(type = FilterType.ASSIGNABLE_TYPE, classes = com.demo.ai.security.HttpMetricsFilter.class),
        @ComponentScan.Filter(type = FilterType.ASSIGNABLE_TYPE, classes = com.demo.ai.security.RequestContextFilter.class)
})
@AutoConfigureMockMvc(addFilters = false)
class IngestionControllerWebMvcTest {
    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private IngestionService ingestionService;
    @MockBean
    private ChatHistoryRepository chatHistoryRepository;
    @MockBean
    private org.springframework.beans.factory.ObjectProvider<Tracer> tracerProvider;
    @MockBean
    private IngestionProperties ingestionProperties;

    @Test
    void shouldAcceptUploadJob() throws Exception {
        MockMultipartFile file = new MockMultipartFile("file", "demo.pdf", "application/pdf", "data".getBytes());
        when(ingestionProperties.getQueueBackend()).thenReturn("redis_stream");
        when(ingestionService.submitPdf(any(), any(), any(), any())).thenReturn(IngestionJob.builder()
                .jobId("job-1")
                .chatId("chat-1")
                .sourceName("demo.pdf")
                .status(IngestionJobStatus.PENDING)
                .attemptCount(0)
                .maxRetries(3)
                .createdAt(LocalDateTime.now())
                .build());

        mockMvc.perform(multipart("/ingestion/upload/chat-1").file(file))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.ok").value(1))
                .andExpect(jsonPath("$.job.jobId").value("job-1"))
                .andExpect(jsonPath("$.job.queueBackend").value("redis_stream"));
    }
}
