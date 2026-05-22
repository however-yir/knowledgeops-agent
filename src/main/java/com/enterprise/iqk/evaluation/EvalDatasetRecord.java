package com.enterprise.iqk.evaluation;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

@TableName("eval_dataset")
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class EvalDatasetRecord {
    @TableId(type = IdType.AUTO)
    private Long id;
    private String datasetId;
    private String tenantId;
    private String name;
    private String description;
    private String baselineRunId;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;
}
