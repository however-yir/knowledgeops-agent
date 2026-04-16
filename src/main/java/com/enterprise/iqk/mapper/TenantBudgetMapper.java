package com.enterprise.iqk.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.enterprise.iqk.domain.TenantBudget;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

@Mapper
public interface TenantBudgetMapper extends BaseMapper<TenantBudget> {

    @Select("""
            SELECT * FROM tenant_budget
            WHERE tenant_id = #{tenantId}
            LIMIT 1
            """)
    TenantBudget findByTenantId(@Param("tenantId") String tenantId);
}
