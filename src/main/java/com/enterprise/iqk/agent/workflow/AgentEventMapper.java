package com.enterprise.iqk.agent.workflow;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

import java.util.List;

@Mapper
public interface AgentEventMapper extends BaseMapper<AgentEventRecord> {

    @Select("SELECT * FROM agent_event WHERE task_id = #{taskId} ORDER BY created_at ASC")
    List<AgentEventRecord> findByTaskId(@Param("taskId") String taskId);

    @Select("SELECT * FROM agent_event WHERE task_id = #{taskId} AND event_type = #{eventType} ORDER BY created_at ASC")
    List<AgentEventRecord> findByTaskIdAndType(@Param("taskId") String taskId,
                                               @Param("eventType") String eventType);
}
