package com.enterprise.iqk.graph;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

import java.util.List;

@Mapper
public interface KgRelationMapper extends BaseMapper<KgRelationRecord> {

    @Select("""
            SELECT r.* FROM kg_relation r
            WHERE r.tenant_id = #{tenantId}
              AND (r.source_entity_id = #{entityId} OR r.target_entity_id = #{entityId})
            """)
    List<KgRelationRecord> findRelations(@Param("tenantId") String tenantId,
                                          @Param("entityId") String entityId);

    @Select("""
            SELECT r.* FROM kg_relation r
            WHERE r.tenant_id = #{tenantId}
              AND r.source_entity_id = #{sourceId}
              AND r.target_entity_id = #{targetId}
            """)
    List<KgRelationRecord> findDirectRelation(@Param("tenantId") String tenantId,
                                               @Param("sourceId") String sourceId,
                                               @Param("targetId") String targetId);

    @Select("""
            SELECT r.* FROM kg_relation r
            WHERE r.tenant_id = #{tenantId}
              AND r.relation_type = #{relationType}
            """)
    List<KgRelationRecord> findByType(@Param("tenantId") String tenantId,
                                       @Param("relationType") String relationType);
}
