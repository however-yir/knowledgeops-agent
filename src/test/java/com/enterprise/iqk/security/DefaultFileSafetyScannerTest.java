package com.enterprise.iqk.security;

import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockMultipartFile;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertThrows;

class DefaultFileSafetyScannerTest {

    private final DefaultFileSafetyScanner scanner = new DefaultFileSafetyScanner();

    @Test
    void shouldAcceptPdfMagicHeader() {
        MockMultipartFile file = new MockMultipartFile(
                "file",
                "doc.pdf",
                "application/pdf",
                "%PDF-1.7\ncontent".getBytes()
        );

        assertDoesNotThrow(() -> scanner.scan(file));
    }

    @Test
    void shouldRejectRenamedNonPdf() {
        MockMultipartFile file = new MockMultipartFile(
                "file",
                "doc.pdf",
                "application/pdf",
                "plain text".getBytes()
        );

        assertThrows(IllegalArgumentException.class, () -> scanner.scan(file));
    }

    @Test
    void shouldRejectEicarSignature() {
        MockMultipartFile file = new MockMultipartFile(
                "file",
                "doc.pdf",
                "application/pdf",
                "%PDF-1.7\nEICAR-STANDARD-ANTIVIRUS-TEST-FILE".getBytes()
        );

        assertThrows(IllegalArgumentException.class, () -> scanner.scan(file));
    }
}
