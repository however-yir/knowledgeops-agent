package com.enterprise.iqk.util;

public final class SqlLikeUtils {
    private SqlLikeUtils() {
    }

    /**
     * Escape MySQL LIKE wildcards so user-supplied keywords cannot widen the
     * search. MySQL's default LIKE escape character is backslash; pass a
     * value through this method before binding it to a {@code LIKE} pattern.
     *
     * <p>Without this, a keyword of {@code %} (or {@code _}, {@code \}) would
     * match every row in the tenant's table, defeating pagination and turning
     * any search endpoint into a one-request DoS / data-exhaustion path.
     */
    public static String escapeForLike(String keyword) {
        if (keyword == null || keyword.isEmpty()) {
            return keyword;
        }
        return keyword
                .replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_");
    }
}
