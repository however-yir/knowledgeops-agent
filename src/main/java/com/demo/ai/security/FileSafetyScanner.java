package com.demo.ai.security;

import org.springframework.web.multipart.MultipartFile;

public interface FileSafetyScanner {
    void scan(MultipartFile file);
}
