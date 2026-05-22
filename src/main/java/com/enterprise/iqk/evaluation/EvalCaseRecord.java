package com.enterprise.iqk.evaluation;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

@TableName("eval_case")
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class EvalCaseRecord {
    @TableId(type = IdType.AUTO)
    private Long id;
    private String caseId;
    private String datasetId;
    private String tenantId;
    private String category;
    private String chatId;
    private String questionText;
    private String expectedCitationsJson;
    private String expectedKeywordsJson;
    private String forbiddenKeywordsJson;
    private Integer sortOrder;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;
}
