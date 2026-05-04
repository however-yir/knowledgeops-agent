package com.enterprise.iqk.graph;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDate;
import java.time.LocalDateTime;

@TableName("kg_fact")
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class KgFactRecord {
    @TableId(type = IdType.AUTO)
    private Long id;
    private String factId;
    private String tenantId;
    private String subject;
    private String predicate;
    private String object;
    private LocalDate validFrom;
    private LocalDate validTo;
    private Double confidence;
    private String source;
    private String metadataJson;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;
}
