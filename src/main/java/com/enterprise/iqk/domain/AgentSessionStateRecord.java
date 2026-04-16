package com.enterprise.iqk.domain;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

@TableName("agent_session_state")
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class AgentSessionStateRecord {
    @TableId(type = IdType.AUTO)
    private Long id;
    private String sessionId;
    private String tenantId;
    private String title;
    private String workspaceId;
    private String modelProfile;
    private Integer streaming;
    private Integer pinned;
    private Integer archived;
    private String activeBranchId;
    private String sessionPayload;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;
}
