package com.enterprise.iqk.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.enterprise.iqk.domain.TenantUsageDaily;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

import java.math.BigDecimal;
import java.time.LocalDate;

@Mapper
public interface TenantUsageDailyMapper extends BaseMapper<TenantUsageDaily> {

    @Insert("""
            INSERT INTO tenant_usage_daily (
              tenant_id,
              usage_date,
              request_count,
              input_tokens,
              output_tokens,
              total_cost_usd,
              created_at,
              updated_at
            ) VALUES (
              #{tenantId},
              #{usageDate},
              #{requestCount},
              #{inputTokens},
              #{outputTokens},
              #{totalCostUsd},
              NOW(),
              NOW()
            )
            ON DUPLICATE KEY UPDATE
              request_count = request_count + VALUES(request_count),
              input_tokens = input_tokens + VALUES(input_tokens),
              output_tokens = output_tokens + VALUES(output_tokens),
              total_cost_usd = total_cost_usd + VALUES(total_cost_usd),
              updated_at = NOW()
            """)
    int addUsage(@Param("tenantId") String tenantId,
                 @Param("usageDate") LocalDate usageDate,
                 @Param("requestCount") long requestCount,
                 @Param("inputTokens") long inputTokens,
                 @Param("outputTokens") long outputTokens,
                 @Param("totalCostUsd") BigDecimal totalCostUsd);

    @Select("""
            SELECT COALESCE(SUM(request_count), 0)
            FROM tenant_usage_daily
            WHERE tenant_id = #{tenantId}
              AND usage_date BETWEEN #{fromDate} AND #{toDate}
            """)
    Long sumRequestCount(@Param("tenantId") String tenantId,
                         @Param("fromDate") LocalDate fromDate,
                         @Param("toDate") LocalDate toDate);

    @Select("""
            SELECT COALESCE(SUM(input_tokens), 0)
            FROM tenant_usage_daily
            WHERE tenant_id = #{tenantId}
              AND usage_date BETWEEN #{fromDate} AND #{toDate}
            """)
    Long sumInputTokens(@Param("tenantId") String tenantId,
                        @Param("fromDate") LocalDate fromDate,
                        @Param("toDate") LocalDate toDate);

    @Select("""
            SELECT COALESCE(SUM(output_tokens), 0)
            FROM tenant_usage_daily
            WHERE tenant_id = #{tenantId}
              AND usage_date BETWEEN #{fromDate} AND #{toDate}
            """)
    Long sumOutputTokens(@Param("tenantId") String tenantId,
                         @Param("fromDate") LocalDate fromDate,
                         @Param("toDate") LocalDate toDate);

    @Select("""
            SELECT COALESCE(SUM(total_cost_usd), 0)
            FROM tenant_usage_daily
            WHERE tenant_id = #{tenantId}
              AND usage_date BETWEEN #{fromDate} AND #{toDate}
            """)
    BigDecimal sumCostUsd(@Param("tenantId") String tenantId,
                          @Param("fromDate") LocalDate fromDate,
                          @Param("toDate") LocalDate toDate);
}
