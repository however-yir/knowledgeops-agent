package com.demo.ai.mapper;

import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

import java.util.List;

@Mapper
public interface PermissionMapper {

    @Select("""
            SELECT p.permission_name
            FROM permissions p
            INNER JOIN role_permissions rp ON p.id = rp.permission_id
            INNER JOIN roles r ON r.id = rp.role_id
            WHERE r.role_name = #{roleName}
            """)
    List<String> findByRoleName(@Param("roleName") String roleName);
}
