FROM eclipse-temurin:17-jre-alpine AS builder
WORKDIR /app

COPY pom.xml .
COPY src ./src

RUN apk add --no-cache maven && \
    mvn -DskipTests package -q && \
    mkdir -p deps && \
    cp target/*.jar deps/app.jar

FROM eclipse-temurin:17-jre-alpine
WORKDIR /app

# Security baseline: run app as non-root user.
RUN addgroup -S appgroup && adduser -S appuser -G appgroup && \
    chown -R appuser:appgroup /app

USER appuser

COPY --from=builder --chown=appuser:appgroup /app/deps/app.jar app.jar

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD wget -q --spider http://localhost:8080/actuator/health || exit 1

EXPOSE 8080

ENTRYPOINT ["java", "-XX:+UseContainerSupport", "-XX:MaxRAMPercentage=75.0", "-Djava.security.egd=file:/dev/./urandom", "-jar", "app.jar"]
