package com.enterprise.iqk.evaluation;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

import java.util.List;

@Mapper
public interface EvalCaseMapper extends BaseMapper<EvalCaseRecord> {

    @Select("""
            SELECT * FROM eval_case
            WHERE tenant_id = #{tenantId}
              AND dataset_id = #{datasetId}
            ORDER BY sort_order ASC, id ASC
            """)
    List<EvalCaseRecord> findByTenantAndDatasetId(@Param("tenantId") String tenantId,
                                                  @Param("datasetId") String datasetId);
}
