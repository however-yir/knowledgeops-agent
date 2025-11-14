package com.enterprise.iqk.domain;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

@TableName("audit_log")
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class AuditLog {
    @TableId(type = IdType.AUTO)
    private Long id;
    private String requestId;
    private String traceId;
    private String userIdentity;
    private String method;
    private String path;
    private Integer statusCode;
    private Long durationMs;
    private String chatId;
    private String jobId;
    private String extraPayload;
    private LocalDateTime createdAt;
}
