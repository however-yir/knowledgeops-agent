package com.enterprise.iqk.graph;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

@TableName("kg_entity")
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class KgEntityRecord {
    @TableId(type = IdType.AUTO)
    private Long id;
    private String entityId;
    private String tenantId;
    private String name;
    private String type;
    private String aliases;      // JSON array
    private String description;
    private String sourceId;
    private String metadataJson;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;
}
