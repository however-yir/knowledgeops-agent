package com.enterprise.iqk.controller;

import com.enterprise.iqk.domain.vo.AnswerFeedbackSubmitVO;
import com.enterprise.iqk.domain.vo.Result;
import com.enterprise.iqk.security.TenantContext;
import com.enterprise.iqk.service.AnswerFeedbackService;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/ai/feedback")
@RequiredArgsConstructor
public class FeedbackController {
    private final AnswerFeedbackService answerFeedbackService;

    @PostMapping
    public Result submit(@RequestHeader(value = TenantContext.TENANT_HEADER, required = false) String tenantId,
                         @RequestBody AnswerFeedbackSubmitVO payload) {
        answerFeedbackService.submit(tenantId, payload);
        return Result.ok();
    }
}
