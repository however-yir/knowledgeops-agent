package com.demo.ai.ingestion;

import com.demo.ai.config.properties.IngestionProperties;
import com.demo.ai.config.properties.RagProperties;
import com.demo.ai.config.properties.VectorStoreProperties;
import com.demo.ai.domain.IngestionJob;
import com.demo.ai.domain.enums.IngestionJobStatus;
import com.demo.ai.ingestion.queue.IngestionQueue;
import com.demo.ai.mapper.IngestionJobMapper;
import com.demo.ai.security.FileSafetyScanner;
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
                .chatId("chat-1")
                .status(com.demo.ai.domain.enums.IngestionJobStatus.PENDING)
                .createdAt(LocalDateTime.now())
                .build();
        when(mapper.findByIdempotencyKey("client:k1")).thenReturn(existing);

        IngestionService service = buildService(mapper, vectorStore, ingestionProperties, vectorStoreProperties, queue, scanner);

        MockMultipartFile file = new MockMultipartFile("file", "a.pdf", "application/pdf", "pdf".getBytes());
        IngestionJob job = service.submitPdf("chat-1", file, "k1", "trace-1");
        assertEquals("job-x", job.getJobId());
        verify(mapper, never()).insert(org.mockito.ArgumentMatchers.<IngestionJob>any());
    }

    @Test
    void shouldCreateNewJob() throws Exception {
        IngestionJobMapper mapper = mock(IngestionJobMapper.class);
        org.springframework.ai.vectorstore.VectorStore vectorStore = mock(org.springframework.ai.vectorstore.VectorStore.class);
        IngestionQueue queue = mock(IngestionQueue.class);
        FileSafetyScanner scanner = mock(FileSafetyScanner.class);
        when(mapper.findByIdempotencyKey(any())).thenReturn(null);

        IngestionProperties ingestionProperties = new IngestionProperties();
        Path temp = Files.createTempDirectory("ingestion-test");
        ingestionProperties.setStorageDir(temp.toString());
        VectorStoreProperties vectorStoreProperties = new VectorStoreProperties();

        IngestionService service = buildService(mapper, vectorStore, ingestionProperties, vectorStoreProperties, queue, scanner);
        MockMultipartFile file = new MockMultipartFile("file", "demo.pdf", "application/pdf", "dummy".getBytes());
        IngestionJob job = service.submitPdf("chat-2", file, null, "trace-x");
        assertNotNull(job.getJobId());
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
