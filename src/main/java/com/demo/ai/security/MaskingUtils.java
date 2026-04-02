package com.demo.ai.security;

public final class MaskingUtils {
    private MaskingUtils() {
    }

    public static String maskContact(String raw) {
        if (raw == null || raw.length() < 7) {
            return "***";
        }
        return raw.substring(0, 3) + "****" + raw.substring(raw.length() - 3);
    }
}
