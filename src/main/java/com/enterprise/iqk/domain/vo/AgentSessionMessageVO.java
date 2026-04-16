package com.enterprise.iqk.domain.vo;

import lombok.Data;

import java.util.List;

@Data
public class AgentSessionMessageVO {
    private String id;
    private String role;
    private String content;
    private Long createdAt;
    private String state;
    private List<String> citations;
    private List<String> evidence;
}
