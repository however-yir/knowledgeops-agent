package com.demo.ai.domain.vo;

import lombok.Builder;
import lombok.Data;

@Data
@Builder
public class IngestionSubmitVO {
    private Integer ok;
    private String msg;
    private IngestionJobVO job;
}
