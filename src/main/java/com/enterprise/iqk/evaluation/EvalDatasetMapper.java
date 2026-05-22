package com.enterprise.iqk.evaluation;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

import java.util.List;

@Mapper
public interface EvalDatasetMapper extends BaseMapper<EvalDatasetRecord> {

    @Select("""
            SELECT * FROM eval_dataset
            WHERE tenant_id = #{tenantId}
              AND dataset_id = #{datasetId}
            LIMIT 1
            """)
    EvalDatasetRecord findByTenantAndDatasetId(@Param("tenantId") String tenantId,
                                               @Param("datasetId") String datasetId);

    @Select("""
            SELECT d.* FROM eval_dataset d
            WHERE d.tenant_id = #{tenantId}
            ORDER BY d.updated_at DESC
            """)
    List<EvalDatasetRecord> findByTenant(@Param("tenantId") String tenantId);

    @Update("""
            UPDATE eval_dataset
            SET baseline_run_id = #{baselineRunId}, updated_at = NOW()
            WHERE tenant_id = #{tenantId}
              AND dataset_id = #{datasetId}
            """)
    int updateBaselineRunId(@Param("tenantId") String tenantId,
                            @Param("datasetId") String datasetId,
                            @Param("baselineRunId") String baselineRunId);
}
