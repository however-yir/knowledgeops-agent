package com.enterprise.iqk.evaluation.vo;

import lombok.Data;

import java.util.List;

@Data
public class EvalCaseCreateVO {
    private String caseId;
    private String category;
    private String chatId;
    private String question;
    private List<String> expectedCitations;
    private List<String> expectedKeywords;
    private List<String> forbiddenKeywords;
}
