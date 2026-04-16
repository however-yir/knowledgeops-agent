package com.enterprise.iqk.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.enterprise.iqk.domain.AgentSessionStateRecord;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

import java.util.List;

@Mapper
public interface AgentSessionStateMapper extends BaseMapper<AgentSessionStateRecord> {

    @Select("""
            SELECT * FROM agent_session_state
            WHERE tenant_id = #{tenantId}
              AND session_id = #{sessionId}
            LIMIT 1
            """)
    AgentSessionStateRecord findByTenantAndSessionId(@Param("tenantId") String tenantId, @Param("sessionId") String sessionId);

    @Select("""
            <script>
            SELECT COUNT(*) FROM agent_session_state
            WHERE tenant_id = #{tenantId}
              <if test="includeArchived == null or includeArchived == false">
                AND archived = 0
              </if>
              <if test="workspaceId != null and workspaceId != '' and workspaceId != 'all'">
                AND workspace_id = #{workspaceId}
              </if>
              <if test="keyword != null and keyword != ''">
                AND (
                  LOWER(title) LIKE CONCAT('%', LOWER(#{keyword}), '%')
                  OR LOWER(session_id) LIKE CONCAT('%', LOWER(#{keyword}), '%')
                )
              </if>
            </script>
            """)
    long countByTenant(@Param("tenantId") String tenantId,
                       @Param("keyword") String keyword,
                       @Param("workspaceId") String workspaceId,
                       @Param("includeArchived") Boolean includeArchived);

    @Select("""
            <script>
            SELECT * FROM agent_session_state
            WHERE tenant_id = #{tenantId}
              <if test="includeArchived == null or includeArchived == false">
                AND archived = 0
              </if>
              <if test="workspaceId != null and workspaceId != '' and workspaceId != 'all'">
                AND workspace_id = #{workspaceId}
              </if>
              <if test="keyword != null and keyword != ''">
                AND (
                  LOWER(title) LIKE CONCAT('%', LOWER(#{keyword}), '%')
                  OR LOWER(session_id) LIKE CONCAT('%', LOWER(#{keyword}), '%')
                )
              </if>
            ORDER BY pinned DESC, updated_at DESC
            LIMIT #{offset}, #{limit}
            </script>
            """)
    List<AgentSessionStateRecord> findByTenant(@Param("tenantId") String tenantId,
                                               @Param("keyword") String keyword,
                                               @Param("workspaceId") String workspaceId,
                                               @Param("includeArchived") Boolean includeArchived,
                                               @Param("offset") long offset,
                                               @Param("limit") int limit);

    @Update("""
            UPDATE agent_session_state
            SET pinned = #{pinned}, updated_at = NOW()
            WHERE tenant_id = #{tenantId}
              AND session_id = #{sessionId}
            """)
    int updatePinned(@Param("tenantId") String tenantId,
                     @Param("sessionId") String sessionId,
                     @Param("pinned") int pinned);

    @Update("""
            UPDATE agent_session_state
            SET archived = #{archived}, updated_at = NOW()
            WHERE tenant_id = #{tenantId}
              AND session_id = #{sessionId}
            """)
    int updateArchived(@Param("tenantId") String tenantId,
                       @Param("sessionId") String sessionId,
                       @Param("archived") int archived);
}
