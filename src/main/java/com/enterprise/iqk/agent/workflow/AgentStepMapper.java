package com.enterprise.iqk.agent.workflow;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

import java.util.List;

@Mapper
public interface AgentStepMapper extends BaseMapper<AgentStepRecord> {

    @Select("SELECT * FROM agent_step WHERE task_id = #{taskId} ORDER BY step_order ASC")
    List<AgentStepRecord> findByTaskId(@Param("taskId") String taskId);

    @Select("SELECT * FROM agent_step WHERE step_id = #{stepId}")
    AgentStepRecord findByStepId(@Param("stepId") String stepId);

    @Update("UPDATE agent_step SET status = #{status}, output_json = #{outputJson}, " +
            "observation_json = #{observationJson}, output_tokens = #{outputTokens}, " +
            "latency_ms = #{latencyMs}, error_message = #{errorMessage}, ended_at = NOW() " +
            "WHERE step_id = #{stepId}")
    int completeStep(@Param("stepId") String stepId,
                     @Param("status") String status,
                     @Param("outputJson") String outputJson,
                     @Param("observationJson") String observationJson,
                     @Param("outputTokens") Long outputTokens,
                     @Param("latencyMs") Long latencyMs,
                     @Param("errorMessage") String errorMessage);
}
