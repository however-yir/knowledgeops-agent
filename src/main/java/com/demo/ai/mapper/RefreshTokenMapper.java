package com.demo.ai.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.demo.ai.domain.RefreshTokenRecord;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

import java.time.LocalDateTime;

@Mapper
public interface RefreshTokenMapper extends BaseMapper<RefreshTokenRecord> {

    @Select("""
            SELECT * FROM refresh_tokens
            WHERE token_hash = #{tokenHash}
              AND revoked_at IS NULL
              AND expires_at > NOW()
            LIMIT 1
            """)
    RefreshTokenRecord findActiveByHash(@Param("tokenHash") String tokenHash);

    @Update("""
            UPDATE refresh_tokens
            SET revoked_at = #{revokedAt}
            WHERE id = #{id}
            """)
    int revoke(@Param("id") Long id, @Param("revokedAt") LocalDateTime revokedAt);
}
