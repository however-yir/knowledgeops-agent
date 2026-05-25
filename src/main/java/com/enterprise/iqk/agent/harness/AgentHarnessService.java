package com.enterprise.iqk.agent.harness;

import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

import java.util.List;

@Service
@RequiredArgsConstructor
public class AgentHarnessService {
    private final List<AgentRuntime> runtimes;
    private final ActionPolicyGuard policyGuard;
    private final HarnessEventRecorder eventRecorder;
    private final HarnessPayloadSanitizer payloadSanitizer;

    public AgentObservation execute(AgentAction action) {
        long startedNs = System.nanoTime();
        ActionPolicyDecision decision = policyGuard.evaluate(action);
        if (!decision.allowed()) {
            AgentObservation observation = AgentObservation.error(
                    "policy",
                    decision.message(),
                    elapsedMs(startedNs)
            );
            eventRecorder.completed(action, observation);
            return observation;
        }

        AgentRuntime runtime = runtimes.stream()
                .filter(candidate -> candidate.supports(action.action()))
                .findFirst()
                .orElse(null);
        if (runtime == null) {
            AgentObservation observation = AgentObservation.error(
                    "runtime",
                    "no runtime for action: " + action.action(),
                    elapsedMs(startedNs)
            );
            eventRecorder.completed(action, observation);
            return observation;
        }

        eventRecorder.started(action, runtime.source());
        AgentObservation observation;
        try {
            observation = runtime.execute(action);
        } catch (RuntimeException ex) {
            observation = AgentObservation.error(runtime.source(), "action failed: " + ex.getMessage(), elapsedMs(startedNs));
        }
        observation = payloadSanitizer.limitObservation(observation);
        eventRecorder.completed(action, observation);
        return observation;
    }

    private long elapsedMs(long startedNs) {
        return java.util.concurrent.TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - startedNs);
    }
}
