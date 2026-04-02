package com.demo.ai.security;

import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.nio.charset.StandardCharsets;

@Component
public class DefaultFileSafetyScanner implements FileSafetyScanner {
    @Override
    public void scan(MultipartFile file) {
        String filename = file.getOriginalFilename() == null ? "" : file.getOriginalFilename().toLowerCase();
        if (!filename.endsWith(".pdf")) {
            throw new IllegalArgumentException("only pdf is allowed");
        }
        try {
            byte[] head = file.getBytes();
            String body = new String(head, StandardCharsets.ISO_8859_1);
            if (StringUtils.hasText(body) && body.contains("EICAR-STANDARD-ANTIVIRUS-TEST-FILE")) {
                throw new IllegalArgumentException("file blocked by malware signature");
            }
        } catch (IOException e) {
            throw new IllegalStateException("file scan failed", e);
        }
    }
}
