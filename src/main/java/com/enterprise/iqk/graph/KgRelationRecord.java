package com.enterprise.iqk.graph;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

@TableName("kg_relation")
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class KgRelationRecord {
    @TableId(type = IdType.AUTO)
    private Long id;
    private String relationId;
    private String tenantId;
    private String sourceEntityId;
    private String targetEntityId;
    private String relationType;
    private String evidenceId;
    private Double weight;
    private String metadataJson;
    private LocalDateTime createdAt;
}
