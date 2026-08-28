package com.enterprise.iqk.config;

import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Stream;

import static org.assertj.core.api.Assertions.assertThat;

class FlywayMigrationVersionTest {

    private static final Pattern VERSIONED_MIGRATION = Pattern.compile("^V(\\d+)__.+\\.sql$");
    private static final Path MIGRATION_DIR = Path.of("src/main/resources/db/migration");

    @Test
    void migrationVersionsAreUniqueAndNotFinderCopies() throws IOException {
        assertThat(MIGRATION_DIR).isDirectory();

        List<String> fileNames;
        try (Stream<Path> stream = Files.list(MIGRATION_DIR)) {
            fileNames = stream
                    .filter(path -> path.getFileName().toString().endsWith(".sql"))
                    .map(path -> path.getFileName().toString())
                    .sorted()
                    .toList();
        }

        Map<String, String> seenVersions = new LinkedHashMap<>();
        Map<String, List<String>> duplicateVersions = new LinkedHashMap<>();
        for (String fileName : fileNames) {
            assertThat(fileName)
                    .as("Flyway migration files must not be Finder copy artifacts")
                    .doesNotContain(" 2.");

            Matcher matcher = VERSIONED_MIGRATION.matcher(fileName);
            assertThat(matcher.matches())
                    .as("Flyway migration name must match V<version>__<description>.sql: %s", fileName)
                    .isTrue();

            String version = matcher.group(1);
            String existing = seenVersions.putIfAbsent(version, fileName);
            if (existing != null) {
                duplicateVersions.put(version, List.of(existing, fileName));
            }
        }

        assertThat(duplicateVersions)
                .as("Flyway version numbers must be unique")
                .isEmpty();
    }
}
