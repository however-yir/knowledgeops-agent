package com.enterprise.iqk.security;

/**
 * Utility for masking sensitive data in audit logs and error messages.
 */
public final class MaskingUtils {

    private static final String MASKED = "***";

    private MaskingUtils() {
    }

    public static String maskContact(String raw) {
        if (raw == null || raw.length() < 7) {
            return MASKED;
        }
        return raw.substring(0, 3) + "****" + raw.substring(raw.length() - 3);
    }

    public static String maskApiKey(String value) {
        if (value == null || value.length() < 8) {
            return MASKED;
        }
        return value.substring(0, 4) + MASKED + value.substring(value.length() - 4);
    }

    public static String maskEmail(String value) {
        if (value == null || !value.contains("@")) {
            return MASKED;
        }
        int atIndex = value.indexOf('@');
        if (atIndex <= 2) {
            return MASKED + value.substring(atIndex);
        }
        return value.charAt(0) + MASKED + value.substring(atIndex);
    }

    public static String maskSensitiveParams(String queryString) {
        if (queryString == null) {
            return null;
        }
        return queryString
                .replaceAll("(?i)(api[_-]?key|token|password|secret|authorization)=([^&]*)", "$1=" + MASKED);
    }
}
