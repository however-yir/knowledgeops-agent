package com.enterprise.iqk.memory;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

@TableName("memory_item")
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class MemoryItemRecord {
    @TableId(type = IdType.AUTO)
    private Long id;
    private String memoryId;
    private String tenantId;
    private String userId;
    private String type;       // short | long | task | fact
    private String content;
    private String source;
    private String sourceTaskId;
    private Double confidence;
    private String metadataJson;
    private LocalDateTime expiresAt;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;
}
