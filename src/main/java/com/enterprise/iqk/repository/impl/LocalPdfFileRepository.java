package com.enterprise.iqk.repository.impl;


import com.enterprise.iqk.config.properties.VectorStoreProperties;
import com.enterprise.iqk.repository.FileRepository;
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.ai.vectorstore.SimpleVectorStore;
import org.springframework.ai.vectorstore.VectorStore;
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;
import org.springframework.stereotype.Component;

import java.io.BufferedReader;
import java.io.File;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.time.LocalDateTime;
import java.util.Properties;

@Slf4j
@Component
@RequiredArgsConstructor
public class LocalPdfFileRepository implements FileRepository {

    private final VectorStore vectorStore;
    private final VectorStoreProperties vectorStoreProperties;

    // 会话id 与 文件名的对应关系，方便查询会话历史时重新加载文件
    private final Properties chatFiles = new Properties();

    @Override
    public boolean save(String chatId, Resource resource) {

        // 2.保存到本地磁盘
        String filename = resource.getFilename();
        if (filename == null || filename.isBlank()) {
            log.error("Resource filename is null or blank.");
            return false;
        }
        File target = new File(filename);
        if (!target.exists()) {
            try {
                Files.copy(resource.getInputStream(), target.toPath());
            } catch (IOException e) {
                log.error("Failed to save PDF resource.", e);
                return false;
            }
        }
        // 3.保存映射关系
        chatFiles.put(chatId, filename);
        return true;
    }

    @Override
    public Resource getFile(String chatId) {
        return new FileSystemResource(chatFiles.getProperty(chatId));
    }

    @PostConstruct
    private void init() {
        FileSystemResource pdfResource = new FileSystemResource("chat-pdf.properties");
        if (pdfResource.exists()) {
            try (BufferedReader reader = new BufferedReader(new InputStreamReader(pdfResource.getInputStream(), StandardCharsets.UTF_8))) {
                chatFiles.load(reader);
            } catch (IOException e) {
                throw new RuntimeException(e);
            }
        }
        FileSystemResource vectorResource = new FileSystemResource(vectorStoreProperties.getSimpleStorePath());
        if (vectorResource.exists() && vectorStore instanceof SimpleVectorStore simpleVectorStore) {
            simpleVectorStore.load(vectorResource);
        }
    }

    @PreDestroy
    private void persistent() {
        try (OutputStreamWriter writer = new OutputStreamWriter(new java.io.FileOutputStream("chat-pdf.properties"), StandardCharsets.UTF_8)) {
            chatFiles.store(writer, LocalDateTime.now().toString());
            if (vectorStore instanceof SimpleVectorStore simpleVectorStore) {
                File target = new File(vectorStoreProperties.getSimpleStorePath());
                File parent = target.getParentFile();
                if (parent != null && !parent.exists()) {
                    if (!parent.mkdirs()) {
                        log.warn("Failed to create parent directories for: {}", parent);
                    }
                }
                simpleVectorStore.save(target);
            }
        } catch (IOException e) {
            throw new RuntimeException(e);
        }
    }
}
