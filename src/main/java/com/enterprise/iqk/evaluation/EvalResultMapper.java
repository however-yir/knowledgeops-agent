package com.enterprise.iqk.evaluation;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

import java.util.List;

@Mapper
public interface EvalResultMapper extends BaseMapper<EvalResultRecord> {

    @Select("""
            SELECT * FROM eval_result
            WHERE tenant_id = #{tenantId}
              AND run_id = #{runId}
            ORDER BY id ASC
            """)
    List<EvalResultRecord> findByTenantAndRunId(@Param("tenantId") String tenantId,
                                                @Param("runId") String runId);
}
