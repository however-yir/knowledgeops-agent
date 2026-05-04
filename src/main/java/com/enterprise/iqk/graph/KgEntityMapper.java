package com.enterprise.iqk.graph;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

import java.util.List;

@Mapper
public interface KgEntityMapper extends BaseMapper<KgEntityRecord> {

    @Select("""
            SELECT * FROM kg_entity
            WHERE tenant_id = #{tenantId}
              AND (name LIKE CONCAT('%', #{keyword}, '%')
                   OR JSON_CONTAINS(aliases, JSON_QUOTE(#{keyword})))
            LIMIT #{limit}
            """)
    List<KgEntityRecord> searchByName(@Param("tenantId") String tenantId,
                                       @Param("keyword") String keyword,
                                       @Param("limit") int limit);

    @Select("SELECT * FROM kg_entity WHERE tenant_id = #{tenantId} AND type = #{type}")
    List<KgEntityRecord> findByType(@Param("tenantId") String tenantId,
                                     @Param("type") String type);

    @Select("SELECT * FROM kg_entity WHERE entity_id = #{entityId}")
    KgEntityRecord findByEntityId(@Param("entityId") String entityId);
}
