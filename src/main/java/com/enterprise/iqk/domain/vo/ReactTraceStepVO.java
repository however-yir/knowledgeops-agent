package com.enterprise.iqk.domain.vo;

import lombok.Builder;
import lombok.Data;

import java.util.Map;

@Data
@Builder
public class ReactTraceStepVO {
    private Integer step;
    private String thought;
    private String action;
    private Map<String, Object> actionInput;
    private Object observation;
}

