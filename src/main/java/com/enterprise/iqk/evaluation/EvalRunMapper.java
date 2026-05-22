package com.enterprise.iqk.evaluation;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

import java.util.List;

@Mapper
public interface EvalRunMapper extends BaseMapper<EvalRunRecord> {

    @Select("""
            SELECT * FROM eval_run
            WHERE tenant_id = #{tenantId}
              AND run_id = #{runId}
            LIMIT 1
            """)
    EvalRunRecord findByTenantAndRunId(@Param("tenantId") String tenantId,
                                       @Param("runId") String runId);

    @Select("""
            SELECT * FROM eval_run
            WHERE tenant_id = #{tenantId}
              AND dataset_id = #{datasetId}
            ORDER BY created_at DESC
            LIMIT #{limit}
            """)
    List<EvalRunRecord> findRecentByDatasetId(@Param("tenantId") String tenantId,
                                              @Param("datasetId") String datasetId,
                                              @Param("limit") int limit);
}
