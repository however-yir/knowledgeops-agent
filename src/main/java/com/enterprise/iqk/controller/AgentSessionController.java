package com.enterprise.iqk.controller;

import com.enterprise.iqk.domain.vo.AgentSessionStateVO;
import com.enterprise.iqk.domain.vo.BranchCompareRequestVO;
import com.enterprise.iqk.domain.vo.BranchCompareResultVO;
import com.enterprise.iqk.domain.vo.BranchMergeRequestVO;
import com.enterprise.iqk.domain.vo.BranchMergeResultVO;
import com.enterprise.iqk.domain.vo.PagedResult;
import com.enterprise.iqk.security.TenantContext;
import com.enterprise.iqk.service.AgentSessionService;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/ai/sessions")
@RequiredArgsConstructor
public class AgentSessionController {
    private final AgentSessionService agentSessionService;

    @GetMapping
    public PagedResult<AgentSessionStateVO> list(@RequestParam(value = "page", defaultValue = "1") int page,
                                                 @RequestParam(value = "pageSize", defaultValue = "20") int pageSize,
                                                 @RequestParam(value = "search", required = false) String search,
                                                 @RequestParam(value = "workspace", required = false) String workspace,
                                                 @RequestParam(value = "includeArchived", defaultValue = "false") boolean includeArchived) {
        return agentSessionService.list(TenantContext.currentTenantId(), search, workspace, includeArchived, page, pageSize);
    }

    @GetMapping("/{sessionId}")
    public AgentSessionStateVO get(@PathVariable("sessionId") String sessionId) {
        return agentSessionService.get(TenantContext.currentTenantId(), sessionId);
    }

    @PutMapping("/{sessionId}")
    public AgentSessionStateVO upsert(@PathVariable("sessionId") String sessionId,
                                      @RequestBody AgentSessionStateVO payload) {
        return agentSessionService.upsert(TenantContext.currentTenantId(), sessionId, payload);
    }

    @PostMapping("/{sessionId}/pin")
    public AgentSessionStateVO setPinned(@PathVariable("sessionId") String sessionId,
                                         @RequestParam("value") boolean value) {
        return agentSessionService.setPinned(TenantContext.currentTenantId(), sessionId, value);
    }

    @PostMapping("/{sessionId}/archive")
    public AgentSessionStateVO setArchived(@PathVariable("sessionId") String sessionId,
                                           @RequestParam("value") boolean value) {
        return agentSessionService.setArchived(TenantContext.currentTenantId(), sessionId, value);
    }

    @PostMapping("/{sessionId}/branches/compare")
    public BranchCompareResultVO compareBranches(@PathVariable("sessionId") String sessionId,
                                                 @RequestBody BranchCompareRequestVO request) {
        if (request == null) {
            throw new IllegalArgumentException("compare request is required");
        }
        return agentSessionService.compareBranches(TenantContext.currentTenantId(), sessionId,
                request.getSourceBranchId(), request.getTargetBranchId());
    }

    @PostMapping("/{sessionId}/branches/merge")
    public BranchMergeResultVO mergeBranches(@PathVariable("sessionId") String sessionId,
                                             @RequestBody BranchMergeRequestVO request) {
        if (request == null) {
            throw new IllegalArgumentException("merge request is required");
        }
        return agentSessionService.mergeBranches(
                TenantContext.currentTenantId(),
                sessionId,
                request.getSourceBranchId(),
                request.getTargetBranchId(),
                request.getTitle()
        );
    }
}
