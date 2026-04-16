package com.enterprise.iqk.domain;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

@TableName("model_ab_exposure")
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class ModelAbExposure {
    @TableId(type = IdType.AUTO)
    private Long id;
    private String tenantId;
    private String experimentKey;
    private String subjectKey;
    private String endpoint;
    private Integer bucket;
    private String variant;
    private String routedProfile;
    private LocalDateTime createdAt;
}
