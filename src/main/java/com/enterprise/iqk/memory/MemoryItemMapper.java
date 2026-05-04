package com.enterprise.iqk.memory;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import org.apache.ibatis.annotations.Delete;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

import java.util.List;

@Mapper
public interface MemoryItemMapper extends BaseMapper<MemoryItemRecord> {

    @Select("""
            SELECT * FROM memory_item
            WHERE tenant_id = #{tenantId}
              AND user_id = #{userId}
              AND type = #{type}
            ORDER BY created_at DESC
            LIMIT #{limit}
            """)
    List<MemoryItemRecord> findByUserAndType(@Param("tenantId") String tenantId,
                                              @Param("userId") String userId,
                                              @Param("type") String type,
                                              @Param("limit") int limit);

    @Select("""
            SELECT * FROM memory_item
            WHERE tenant_id = #{tenantId}
              AND user_id = #{userId}
            ORDER BY created_at DESC
            LIMIT #{limit}
            """)
    List<MemoryItemRecord> findByUser(@Param("tenantId") String tenantId,
                                       @Param("userId") String userId,
                                       @Param("limit") int limit);

    @Select("SELECT * FROM memory_item WHERE source_task_id = #{taskId}")
    List<MemoryItemRecord> findByTaskId(@Param("taskId") String taskId);

    @Select("""
            SELECT * FROM memory_item
            WHERE tenant_id = #{tenantId}
              AND type = #{type}
              AND confidence >= #{minConfidence}
            ORDER BY created_at DESC
            LIMIT #{limit}
            """)
    List<MemoryItemRecord> findByTypeAndConfidence(@Param("tenantId") String tenantId,
                                                    @Param("type") String type,
                                                    @Param("minConfidence") double minConfidence,
                                                    @Param("limit") int limit);

    @Select("SELECT * FROM memory_item WHERE memory_id = #{memoryId}")
    MemoryItemRecord findByMemoryId(@Param("memoryId") String memoryId);

    @Delete("DELETE FROM memory_item WHERE expires_at IS NOT NULL AND expires_at < NOW()")
    int deleteExpired();
}
