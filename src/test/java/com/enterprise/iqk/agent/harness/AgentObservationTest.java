package com.enterprise.iqk.agent.harness;

import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

class AgentObservationTest {

    @Test
    void toMapPreservesPayloadStatusAndTopLevelFields() {
        AgentObservation observation = AgentObservation.success(
                "builtin",
                Map.of(
                        "status", "created",
                        "reservationId", "r-1",
                        "citations", List.of("source=a")
                ),
                12
        );

        Map<String, Object> payload = observation.toMap();

        assertThat(payload)
                .containsEntry("status", "created")
                .containsEntry("reservationId", "r-1")
                .containsEntry("source", "builtin")
                .containsEntry("latencyMs", 12L);
        assertThat(payload.get("citations")).isEqualTo(List.of("source=a"));
    }

    @Test
    void toMapWrapsNonMapPayloadAsData() {
        AgentObservation observation = AgentObservation.success("builtin", List.of("school"), 3);

        assertThat(observation.toMap())
                .containsEntry("status", "success")
                .containsEntry("data", List.of("school"))
                .containsEntry("source", "builtin");
    }
}
