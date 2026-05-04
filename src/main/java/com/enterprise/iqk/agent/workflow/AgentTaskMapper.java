package com.enterprise.iqk.agent.workflow;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

import java.util.List;

@Mapper
public interface AgentTaskMapper extends BaseMapper<AgentTaskRecord> {

    @Select("SELECT * FROM agent_task WHERE task_id = #{taskId}")
    AgentTaskRecord findByTaskId(@Param("taskId") String taskId);

    @Select("SELECT * FROM agent_task WHERE tenant_id = #{tenantId} ORDER BY created_at DESC LIMIT #{limit} OFFSET #{offset}")
    List<AgentTaskRecord> findByTenant(@Param("tenantId") String tenantId,
                                       @Param("offset") long offset,
                                       @Param("limit") int limit);

    @Select("SELECT COUNT(*) FROM agent_task WHERE tenant_id = #{tenantId}")
    long countByTenant(@Param("tenantId") String tenantId);

    @Select("SELECT * FROM agent_task WHERE tenant_id = #{tenantId} AND type = #{type} ORDER BY created_at DESC LIMIT #{limit} OFFSET #{offset}")
    List<AgentTaskRecord> findByTenantAndType(@Param("tenantId") String tenantId,
                                              @Param("type") String type,
                                              @Param("offset") long offset,
                                              @Param("limit") int limit);

    @Update("UPDATE agent_task SET status = #{status}, updated_at = NOW() WHERE task_id = #{taskId}")
    int updateStatus(@Param("taskId") String taskId, @Param("status") String status);

    @Update("UPDATE agent_task SET status = #{status}, final_output = #{finalOutput}, updated_at = NOW() WHERE task_id = #{taskId}")
    int completeTask(@Param("taskId") String taskId,
                     @Param("status") String status,
                     @Param("finalOutput") String finalOutput);
}
