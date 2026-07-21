package com.enterprise.iqk.memory;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.util.Collections;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class MemoryServiceTenantIsolationTest {

    private MemoryItemMapper itemMapper;
    private MemoryEventMapper eventMapper;
    private MemoryService service;

    @BeforeEach
    void setUp() {
        itemMapper = mock(MemoryItemMapper.class);
        eventMapper = mock(MemoryEventMapper.class);
        service = new MemoryService(itemMapper, eventMapper, new ObjectMapper());
    }

    @Test
    void savesAndBuildsTenantScopedMemoryContext() {
        MemoryItemRecord saved = service.saveShortMemory(
                "tenant-a", "user-1", "  prefers Java  ", "chat-1");
        MemoryItemRecord longMemory = MemoryItemRecord.builder().content("backend engineer").build();
        MemoryItemRecord shortMemory = MemoryItemRecord.builder().content("prefers Java").build();
        MemoryItemRecord factMemory = MemoryItemRecord.builder().content("uses Spring Boot").build();
        when(itemMapper.findByUserAndType("tenant-a", "user-1", "short", 5))
                .thenReturn(List.of(shortMemory));
        when(itemMapper.findByUserAndType("tenant-a", "user-1", "long", 10))
                .thenReturn(List.of(longMemory));
        when(itemMapper.findByTypeAndConfidence("tenant-a", "fact", 0.7, 5))
                .thenReturn(List.of(factMemory));

        MemoryService.MemoryContextSnapshot context = service.buildContext("tenant-a", "user-1");

        assertThat(saved.getTenantId()).isEqualTo("tenant-a");
        assertThat(saved.getContent()).isEqualTo("prefers Java");
        assertThat(context.contextText()).contains("backend engineer", "prefers Java");
        assertThat(context.facts()).containsExactly(factMemory);
        verify(itemMapper).insert(saved);
    }

    @Test
    void taskQueryDeleteAndEventsCannotCrossTenantBoundary() {
        when(itemMapper.findByTenantAndTaskId("tenant-b", "task-a"))
                .thenReturn(Collections.emptyList());
        when(itemMapper.findByTenantAndMemoryId("tenant-b", "memory-a"))
                .thenReturn(null);

        assertThat(service.queryTaskMemory("tenant-b", "task-a")).isEmpty();
        service.deleteMemory("tenant-b", "memory-a");
        assertThat(service.getEvents("tenant-b", "memory-a")).isEmpty();

        verify(itemMapper, never()).deleteById(
                (java.io.Serializable) org.mockito.ArgumentMatchers.any());
        verify(eventMapper, never()).findByMemoryId("memory-a");
    }
}
