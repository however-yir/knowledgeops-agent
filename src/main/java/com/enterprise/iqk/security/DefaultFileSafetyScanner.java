package com.enterprise.iqk.security;

import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.Locale;

@Component
public class DefaultFileSafetyScanner implements FileSafetyScanner {
    private static final int SCAN_BYTES = 8192;

    @Override
    public void scan(MultipartFile file) {
        String originalName = file.getOriginalFilename();
        String filename = originalName == null ? "" : originalName.toLowerCase(Locale.ROOT);
        if (!filename.endsWith(".pdf")) {
            throw new IllegalArgumentException("only pdf is allowed");
        }
        try {
            byte[] head = readHead(file);
            String body = new String(head, StandardCharsets.ISO_8859_1);
            if (!body.startsWith("%PDF-")) {
                throw new IllegalArgumentException("invalid pdf header");
            }
            if (StringUtils.hasText(body) && body.contains("EICAR-STANDARD-ANTIVIRUS-TEST-FILE")) {
                throw new IllegalArgumentException("file blocked by malware signature");
            }
        } catch (IOException e) {
            throw new IllegalStateException("file scan failed", e);
        }
    }

    private byte[] readHead(MultipartFile file) throws IOException {
        try (InputStream inputStream = file.getInputStream()) {
            if (inputStream == null) {
                throw new IOException("input stream is null");
            }
            return inputStream.readNBytes(SCAN_BYTES);
        }
    }
}
