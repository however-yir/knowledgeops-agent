# syntax=docker/dockerfile:1.7
FROM maven:3.9.9-eclipse-temurin-17 AS builder
WORKDIR /app

COPY pom.xml .
COPY checkstyle.xml pmd-ruleset.xml spotbugs-exclude.xml owasp-suppressions.xml ./
COPY src ./src

RUN --mount=type=cache,target=/root/.m2 \
    mvn -DskipTests package -q && \
    mkdir -p deps && \
    cp target/*.jar deps/app.jar

FROM eclipse-temurin:17-jre
WORKDIR /app

RUN groupadd --system appgroup && \
    useradd --system --gid appgroup appuser && \
    mkdir -p /app/data /app/logs && \
    chown -R appuser:appgroup /app && \
    chmod -R 750 /app

USER appuser

COPY --from=builder --chown=appuser:appgroup /app/deps/app.jar app.jar

# Read-only root filesystem support
VOLUME ["/app/data", "/app/logs"]

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8080/actuator/health || exit 1

EXPOSE 8080

ENV JAVA_OPTS="-XX:+UseContainerSupport -XX:MaxRAMPercentage=75.0 -XX:+UseG1GC -XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=/app/logs/heapdump.hprof -Djava.security.egd=file:/dev/./urandom"

ENTRYPOINT exec java $JAVA_OPTS -jar app.jar
