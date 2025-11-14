package com.enterprise.iqk.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.enterprise.iqk.domain.IngestionJob;
import com.enterprise.iqk.domain.enums.IngestionJobStatus;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

import java.time.LocalDateTime;
import java.util.List;

@Mapper
public interface IngestionJobMapper extends BaseMapper<IngestionJob> {

    @Select("SELECT * FROM ingestion_job WHERE idempotency_key = #{idempotencyKey} LIMIT 1")
    IngestionJob findByIdempotencyKey(@Param("idempotencyKey") String idempotencyKey);

    @Select("SELECT * FROM ingestion_job WHERE job_id = #{jobId} LIMIT 1")
    IngestionJob findByJobId(@Param("jobId") String jobId);

    @Select("""
            SELECT * FROM ingestion_job
            WHERE status IN ('PENDING','RETRY')
              AND (next_retry_at IS NULL OR next_retry_at <= #{now})
            ORDER BY created_at ASC
            LIMIT 1
            """)
    IngestionJob findNextReadyJob(@Param("now") LocalDateTime now);

    @Update("""
            UPDATE ingestion_job
            SET status = #{toStatus},
                started_at = #{startedAt},
                updated_at = #{updatedAt},
                attempt_count = attempt_count + 1,
                error_message = NULL
            WHERE job_id = #{jobId} AND status IN ('PENDING','RETRY')
            """)
    int claimForRun(@Param("jobId") String jobId,
                    @Param("toStatus") IngestionJobStatus toStatus,
                    @Param("startedAt") LocalDateTime startedAt,
                    @Param("updatedAt") LocalDateTime updatedAt);

    @Update("""
            UPDATE ingestion_job
            SET status = #{status},
                finished_at = #{finishedAt},
                updated_at = #{updatedAt},
                error_message = #{errorMessage},
                next_retry_at = #{nextRetryAt}
            WHERE job_id = #{jobId}
            """)
    int updateTerminalState(@Param("jobId") String jobId,
                            @Param("status") IngestionJobStatus status,
                            @Param("finishedAt") LocalDateTime finishedAt,
                            @Param("updatedAt") LocalDateTime updatedAt,
                            @Param("errorMessage") String errorMessage,
                            @Param("nextRetryAt") LocalDateTime nextRetryAt);

    @Select("SELECT * FROM ingestion_job WHERE chat_id = #{chatId} ORDER BY created_at DESC LIMIT #{limit}")
    List<IngestionJob> findLatestByChatId(@Param("chatId") String chatId, @Param("limit") int limit);

    @Select("""
            SELECT * FROM ingestion_job
            WHERE status = 'RETRY'
              AND next_retry_at IS NOT NULL
              AND next_retry_at <= #{now}
            ORDER BY next_retry_at ASC
            LIMIT #{limit}
            """)
    List<IngestionJob> findReadyRetries(@Param("now") LocalDateTime now, @Param("limit") int limit);

    @Update("""
            UPDATE ingestion_job
            SET status = 'PENDING',
                updated_at = #{updatedAt},
                next_retry_at = NULL
            WHERE job_id = #{jobId}
              AND status = 'RETRY'
            """)
    int requeueRetry(@Param("jobId") String jobId, @Param("updatedAt") LocalDateTime updatedAt);
}
