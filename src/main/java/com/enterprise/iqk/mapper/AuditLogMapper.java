package com.enterprise.iqk.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.enterprise.iqk.domain.AuditLog;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

import java.time.LocalDateTime;
import java.util.List;

@Mapper
public interface AuditLogMapper extends BaseMapper<AuditLog> {
    @Update("DELETE FROM audit_log WHERE created_at < #{deadline}")
    int deleteBefore(@Param("deadline") LocalDateTime deadline);

    @Select("SELECT * FROM audit_log ORDER BY created_at DESC LIMIT #{limit}")
    List<AuditLog> latest(@Param("limit") int limit);

    @Select("""
            SELECT * FROM audit_log
            WHERE tenant_id = #{tenantId}
            ORDER BY created_at DESC
            LIMIT #{limit}
            """)
    List<AuditLog> latestByTenant(@Param("tenantId") String tenantId, @Param("limit") int limit);
}
