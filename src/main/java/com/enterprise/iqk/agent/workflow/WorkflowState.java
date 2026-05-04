package com.enterprise.iqk.agent.workflow;

public enum WorkflowState {
    CREATED,
    PLANNING,
    SEARCHING,
    RETRIEVING,
    JUDGING,
    REFLECTING,
    WRITING,
    DONE,
    NEED_MORE_EVIDENCE,
    FAILED;

    public boolean isTerminal() {
        return this == DONE || this == FAILED;
    }

    public boolean canTransitionTo(WorkflowState target) {
        return switch (this) {
            case CREATED -> target == PLANNING;
            case PLANNING -> target == SEARCHING || target == RETRIEVING || target == WRITING || target == FAILED;
            case SEARCHING -> target == RETRIEVING || target == JUDGING || target == FAILED;
            case RETRIEVING -> target == JUDGING || target == REFLECTING || target == FAILED;
            case JUDGING -> target == REFLECTING || target == WRITING || target == FAILED;
            case REFLECTING -> target == WRITING || target == NEED_MORE_EVIDENCE || target == FAILED;
            case NEED_MORE_EVIDENCE -> target == SEARCHING || target == RETRIEVING || target == FAILED;
            case WRITING -> target == DONE || target == FAILED;
            case DONE, FAILED -> false;
        };
    }
}
