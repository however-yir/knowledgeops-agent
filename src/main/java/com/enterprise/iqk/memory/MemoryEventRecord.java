package com.enterprise.iqk.memory;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

@TableName("memory_event")
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class MemoryEventRecord {
    @TableId(type = IdType.AUTO)
    private Long id;
    private String eventId;
    private String memoryId;
    private String action;     // CREATE | UPDATE | DELETE | EXPIRE | HIT | USE
    private String reason;
    private String metadataJson;
    private LocalDateTime createdAt;
}
