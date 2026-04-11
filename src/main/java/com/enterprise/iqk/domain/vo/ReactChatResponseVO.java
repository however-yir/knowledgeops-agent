package com.enterprise.iqk.domain.vo;

import lombok.Builder;
import lombok.Data;

import java.util.List;

@Data
@Builder
public class ReactChatResponseVO {
    private Integer ok;
    private String msg;
    private String chatId;
    private String answer;
    private List<ReactTraceStepVO> trace;
}

