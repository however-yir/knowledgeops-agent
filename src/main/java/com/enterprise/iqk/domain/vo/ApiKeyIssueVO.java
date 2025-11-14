package com.enterprise.iqk.domain.vo;

import lombok.Builder;
import lombok.Data;

import java.time.LocalDateTime;

@Data
@Builder
public class ApiKeyIssueVO {
    private Integer ok;
    private String msg;
    private String keyName;
    private String rawApiKey;
    private LocalDateTime expiresAt;
}
