package com.enterprise.iqk.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.enterprise.iqk.domain.Conversation;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

import java.util.List;

@Mapper
public interface ConversationMapper extends BaseMapper<Conversation> {
    @Select("""
            SELECT COUNT(DISTINCT conversation_id)
            FROM conversation
            WHERE tenant_id = #{tenantId}
              AND conversation_id LIKE CONCAT(#{type}, '::%')
            """)
    long countConversationIdsByType(@Param("tenantId") String tenantId, @Param("type") String type);

    @Select("""
            SELECT conversation_id
            FROM conversation
            WHERE tenant_id = #{tenantId}
              AND conversation_id LIKE CONCAT(#{type}, '::%')
            GROUP BY conversation_id
            ORDER BY MAX(create_time) DESC
            LIMIT #{offset}, #{limit}
            """)
    List<String> findConversationIdsByType(@Param("tenantId") String tenantId,
                                           @Param("type") String type,
                                           @Param("offset") long offset,
                                           @Param("limit") int limit);

    @Select("""
            SELECT id, tenant_id, conversation_id, message, type, create_time
            FROM conversation
            WHERE tenant_id = #{tenantId}
              AND conversation_id = #{conversationId}
            ORDER BY create_time DESC
            LIMIT #{offset}, #{limit}
            """)
    List<Conversation> findMessagesByConversationId(@Param("tenantId") String tenantId,
                                                    @Param("conversationId") String conversationId,
                                                    @Param("offset") long offset,
                                                    @Param("limit") int limit);

    @Select("""
            SELECT COUNT(*)
            FROM conversation
            WHERE tenant_id = #{tenantId}
              AND conversation_id = #{conversationId}
            """)
    long countMessagesByConversationId(@Param("tenantId") String tenantId, @Param("conversationId") String conversationId);

    @Select("""
            SELECT id, tenant_id, conversation_id, message, type, create_time
            FROM conversation
            WHERE tenant_id = #{tenantId}
              AND conversation_id = #{conversationId}
            ORDER BY create_time DESC
            LIMIT #{limit}
            """)
    List<Conversation> findLatestMessages(@Param("tenantId") String tenantId,
                                          @Param("conversationId") String conversationId,
                                          @Param("limit") int limit);
}
