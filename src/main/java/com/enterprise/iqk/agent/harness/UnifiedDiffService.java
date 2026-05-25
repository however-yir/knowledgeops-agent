package com.enterprise.iqk.agent.harness;

import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

@Component
public class UnifiedDiffService {
    private static final Pattern HUNK_HEADER = Pattern.compile("@@ -(\\d+)(?:,(\\d+))? \\+(\\d+)(?:,(\\d+))? @@.*");

    public String create(String path, String oldContent, String newContent) {
        List<String> oldLines = splitLines(oldContent);
        List<String> newLines = splitLines(newContent);
        StringBuilder builder = new StringBuilder();
        builder.append("--- a/").append(path).append('\n');
        builder.append("+++ b/").append(path).append('\n');
        builder.append("@@ -1,").append(oldLines.size())
                .append(" +1,").append(newLines.size()).append(" @@\n");
        for (String line : oldLines) {
            builder.append('-').append(line).append('\n');
        }
        for (String line : newLines) {
            builder.append('+').append(line).append('\n');
        }
        return builder.toString();
    }

    public String apply(String oldContent, String patch) {
        List<String> oldLines = splitLines(oldContent);
        List<String> patchLines = splitLines(patch);
        List<String> result = new ArrayList<>();
        int oldIndex = 0;
        int patchIndex = 0;
        while (patchIndex < patchLines.size()) {
            String line = patchLines.get(patchIndex);
            if (!line.startsWith("@@ ")) {
                patchIndex++;
                continue;
            }
            Matcher matcher = HUNK_HEADER.matcher(line);
            if (!matcher.matches()) {
                throw new IllegalArgumentException("invalid patch hunk header");
            }
            int oldStart = Integer.parseInt(matcher.group(1));
            int targetOldIndex = Math.max(0, oldStart - 1);
            while (oldIndex < targetOldIndex && oldIndex < oldLines.size()) {
                result.add(oldLines.get(oldIndex++));
            }
            patchIndex++;
            while (patchIndex < patchLines.size() && !patchLines.get(patchIndex).startsWith("@@ ")) {
                String body = patchLines.get(patchIndex++);
                if (body.isEmpty()) {
                    continue;
                }
                char prefix = body.charAt(0);
                String content = body.substring(1);
                if (prefix == ' ') {
                    if (oldIndex < oldLines.size()) {
                        result.add(oldLines.get(oldIndex++));
                    } else {
                        result.add(content);
                    }
                } else if (prefix == '-') {
                    oldIndex++;
                } else if (prefix == '+') {
                    result.add(content);
                }
            }
        }
        while (oldIndex < oldLines.size()) {
            result.add(oldLines.get(oldIndex++));
        }
        return String.join("\n", result);
    }

    private List<String> splitLines(String content) {
        if (content == null || content.isEmpty()) {
            return List.of();
        }
        String normalized = content.endsWith("\n") ? content.substring(0, content.length() - 1) : content;
        if (normalized.isEmpty()) {
            return List.of();
        }
        return List.of(normalized.split("\\n", -1));
    }
}
