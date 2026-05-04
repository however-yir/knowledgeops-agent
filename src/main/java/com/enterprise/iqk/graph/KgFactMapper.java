package com.enterprise.iqk.graph;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

import java.util.List;

@Mapper
public interface KgFactMapper extends BaseMapper<KgFactRecord> {

    @Select("""
            SELECT * FROM kg_fact
            WHERE tenant_id = #{tenantId}
              AND (subject LIKE CONCAT('%', #{keyword}, '%')
                   OR object LIKE CONCAT('%', #{keyword}, '%'))
            ORDER BY confidence DESC
            LIMIT #{limit}
            """)
    List<KgFactRecord> searchByKeyword(@Param("tenantId") String tenantId,
                                        @Param("keyword") String keyword,
                                        @Param("limit") int limit);

    @Select("SELECT * FROM kg_fact WHERE tenant_id = #{tenantId} AND subject = #{subject}")
    List<KgFactRecord> findBySubject(@Param("tenantId") String tenantId,
                                      @Param("subject") String subject);
}
