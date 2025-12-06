package com.enterprise.iqk.domain.vo;

import lombok.Builder;
import lombok.Data;

import java.time.LocalDateTime;

@Data
@Builder
public class AuthTokenVO {
    private Integer ok;
    private String msg;
    private String token;
    private String refreshToken;
    private String tenantId;
    private Long expiresInSeconds;
    private LocalDateTime refreshExpiresAt;
    private Boolean refreshWillExpireSoon;
}
