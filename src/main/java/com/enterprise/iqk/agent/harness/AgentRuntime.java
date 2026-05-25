package com.enterprise.iqk.agent.harness;

public interface AgentRuntime {
    String source();

    boolean supports(String action);

    AgentObservation execute(AgentAction action);
}
