package com.enterprise.iqk.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.enterprise.iqk.domain.ApiKeyRecord;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

import java.time.LocalDateTime;

@Mapper
public interface ApiKeyMapper extends BaseMapper<ApiKeyRecord> {

    @Select("""
            SELECT * FROM api_keys
            WHERE key_hash = #{keyHash}
              AND enabled = 1
              AND revoked_at IS NULL
              AND (expires_at IS NULL OR expires_at > NOW())
            LIMIT 1
            """)
    ApiKeyRecord findActiveByKeyHash(@Param("keyHash") String keyHash);

    @Update("UPDATE api_keys SET last_used_at = #{lastUsedAt}, updated_at = #{updatedAt} WHERE id = #{id}")
    int touch(@Param("id") Long id, @Param("lastUsedAt") LocalDateTime lastUsedAt, @Param("updatedAt") LocalDateTime updatedAt);

    @Select("""
            SELECT * FROM api_keys
            WHERE key_name = #{keyName}
              AND tenant_id = #{tenantId}
              AND enabled = 1
              AND revoked_at IS NULL
              AND (expires_at IS NULL OR expires_at > NOW())
            ORDER BY id DESC
            LIMIT 1
            """)
    ApiKeyRecord findActiveByKeyName(@Param("keyName") String keyName, @Param("tenantId") String tenantId);

    @Select("""
            SELECT * FROM api_keys
            WHERE key_name = #{keyName}
              AND tenant_id = #{tenantId}
            ORDER BY id DESC
            LIMIT 1
            """)
    ApiKeyRecord findLatestByKeyName(@Param("keyName") String keyName, @Param("tenantId") String tenantId);

    @Update("""
            UPDATE api_keys
            SET enabled = 0,
                revoked_at = #{revokedAt},
                revoked_reason = #{reason},
                updated_at = #{updatedAt}
            WHERE id = #{id}
            """)
    int revoke(@Param("id") Long id,
               @Param("revokedAt") LocalDateTime revokedAt,
               @Param("reason") String reason,
               @Param("updatedAt") LocalDateTime updatedAt);
}
