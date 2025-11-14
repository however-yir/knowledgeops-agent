package com.enterprise.iqk.domain;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

@TableName("api_keys")
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class ApiKeyRecord {
    @TableId(type = IdType.AUTO)
    private Long id;
    private String keyHash;
    private String keyName;
    private String roleName;
    private Integer enabled;
    private LocalDateTime lastUsedAt;
    private LocalDateTime expiresAt;
    private LocalDateTime revokedAt;
    private String revokedReason;
    private Long rotatedFromId;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;
}
