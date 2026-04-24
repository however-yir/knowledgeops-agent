package com.enterprise.iqk.ingestion;

import com.enterprise.iqk.config.properties.IngestionProperties;
import com.enterprise.iqk.config.properties.RagProperties;
import com.enterprise.iqk.config.properties.VectorStoreProperties;
import com.enterprise.iqk.domain.IngestionJob;
import com.enterprise.iqk.domain.enums.IngestionJobStatus;
import com.enterprise.iqk.ingestion.queue.IngestionQueue;
import com.enterprise.iqk.mapper.IngestionJobMapper;
import com.enterprise.iqk.security.FileSafetyScanner;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockMultipartFile;

import java.nio.file.Files;
import java.nio.file.Path;
import java.time.LocalDateTime;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class IngestionServiceTest {

    private IngestionService buildService(IngestionJobMapper mapper,
                                          org.springframework.ai.vectorstore.VectorStore vectorStore,
                                          IngestionProperties ingestionProperties,
                                          VectorStoreProperties vectorStoreProperties,
                                          IngestionQueue queue,
                                          FileSafetyScanner scanner) {
        return new IngestionService(
                mapper,
                vectorStore,
                ingestionProperties,
                vectorStoreProperties,
                new RagProperties(),
                new SimpleMeterRegistry(),
                queue,
                scanner
        );
    }

    @Test
    void shouldReuseExistingJobByIdempotencyKey() {
        IngestionJobMapper mapper = mock(IngestionJobMapper.class);
        org.springframework.ai.vectorstore.VectorStore vectorStore = mock(org.springframework.ai.vectorstore.VectorStore.class);
        IngestionQueue queue = mock(IngestionQueue.class);
        FileSafetyScanner scanner = mock(FileSafetyScanner.class);

        IngestionProperties ingestionProperties = new IngestionProperties();
        VectorStoreProperties vectorStoreProperties = new VectorStoreProperties();
        IngestionJob existing = IngestionJob.builder()
                .jobId("job-x")
                .tenantId("public")
                .chatId("chat-1")
                .status(com.enterprise.iqk.domain.enums.IngestionJobStatus.PENDING)
                .createdAt(LocalDateTime.now())
                .build();
        when(mapper.findByIdempotencyKey("public", "client:k1")).thenReturn(existing);

        IngestionService service = buildService(mapper, vectorStore, ingestionProperties, vectorStoreProperties, queue, scanner);

        MockMultipartFile file = new MockMultipartFile("file", "a.pdf", "application/pdf", "pdf".getBytes());
        IngestionJob job = service.submitPdf("public", "chat-1", file, "k1", "trace-1");
        assertEquals("job-x", job.getJobId());
        verify(mapper, never()).insert(org.mockito.ArgumentMatchers.<IngestionJob>any());
    }

    @Test
    void shouldCreateNewJob() throws Exception {
        IngestionJobMapper mapper = mock(IngestionJobMapper.class);
        org.springframework.ai.vectorstore.VectorStore vectorStore = mock(org.springframework.ai.vectorstore.VectorStore.class);
        IngestionQueue queue = mock(IngestionQueue.class);
        FileSafetyScanner scanner = mock(FileSafetyScanner.class);
        when(mapper.findByIdempotencyKey(anyString(), anyString())).thenReturn(null);

        IngestionProperties ingestionProperties = new IngestionProperties();
        Path temp = Files.createTempDirectory("ingestion-test");
        ingestionProperties.setStorageDir(temp.toString());
        VectorStoreProperties vectorStoreProperties = new VectorStoreProperties();

        IngestionService service = buildService(mapper, vectorStore, ingestionProperties, vectorStoreProperties, queue, scanner);
        MockMultipartFile file = new MockMultipartFile("file", "sample.pdf", "application/pdf", "dummy".getBytes());
        IngestionJob job = service.submitPdf("public", "chat-2", file, null, "trace-x");
        assertNotNull(job.getJobId());
        assertEquals("public", job.getTenantId());
        assertEquals("chat-2", job.getChatId());
        verify(mapper).insert(org.mockito.ArgumentMatchers.<IngestionJob>any());
        verify(queue).publishJob(any(), any());
    }

    @Test
    void shouldNotPickMissingQueuedJob() {
        IngestionJobMapper mapper = mock(IngestionJobMapper.class);
        org.springframework.ai.vectorstore.VectorStore vectorStore = mock(org.springframework.ai.vectorstore.VectorStore.class);
        IngestionQueue queue = mock(IngestionQueue.class);
        FileSafetyScanner scanner = mock(FileSafetyScanner.class);
        when(mapper.claimForRun(any(), any(), any(), any())).thenReturn(0);

        IngestionService service = buildService(
                mapper, vectorStore, new IngestionProperties(), new VectorStoreProperties(), queue, scanner
        );
        IngestionProcessResult result = service.processQueuedJob("job-1", "trace-a");
        assertFalse(result.isPicked());
        assertEquals(IngestionJobStatus.RUNNING, result.getStatus());
    }
}
