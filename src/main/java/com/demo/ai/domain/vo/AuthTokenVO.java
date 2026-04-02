package com.demo.ai.domain.vo;

import lombok.Builder;
import lombok.Data;

@Data
@Builder
public class AuthTokenVO {
    private Integer ok;
    private String msg;
    private String token;
    private String refreshToken;
    private Long expiresInSeconds;
}
