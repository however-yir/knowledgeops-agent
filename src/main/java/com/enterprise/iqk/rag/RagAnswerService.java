package com.enterprise.iqk.rag;

import com.enterprise.iqk.config.properties.RagProperties;
import lombok.Builder;
import lombok.Data;
import lombok.RequiredArgsConstructor;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.document.Document;
import org.springframework.ai.vectorstore.SearchRequest;
import org.springframework.ai.vectorstore.VectorStore;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import java.util.*;
import java.util.stream.Collectors;

import static org.springframework.ai.chat.client.advisor.AbstractChatMemoryAdvisor.CHAT_MEMORY_CONVERSATION_ID_KEY;

@Service
@RequiredArgsConstructor
public class RagAnswerService {

    private final VectorStore vectorStore;
    private final ChatClient chatClient;
    private final RagProperties ragProperties;

    public RagResult answer(String prompt, String chatId, String conversationId) {
        String filterExpression = "chat_id == '" + chatId.replace("'", "") + "'";
        SearchRequest request = SearchRequest.builder()
                .query(prompt)
                .topK(ragProperties.getRetrieveTopK())
                .similarityThreshold(ragProperties.getSimilarityThreshold())
                .filterExpression(filterExpression)
                .build();
        List<Document> retrieved = vectorStore.similaritySearch(request);
        if (retrieved == null || retrieved.isEmpty()) {
            return RagResult.builder()
                    .answer("没有在当前知识库中检索到可用内容。")
                    .citations(List.of())
                    .build();
        }
        List<Document> reranked = rerank(prompt, retrieved);
        List<Document> selected = reranked.stream()
                .limit(Math.max(1, ragProperties.getRerankTopK()))
                .toList();
        String context = buildContext(selected);
        String answer = chatClient.prompt()
                .system("你是一个RAG问答助手。必须仅根据给定上下文作答，输出结尾附上引用编号，例如 [1][2]。如果上下文不足请明确说明。")
                .user("""
                        用户问题:
                        %s

                        上下文:
                        %s
                        """.formatted(prompt, context))
                .advisors(a -> a.param(CHAT_MEMORY_CONVERSATION_ID_KEY, conversationId))
                .call()
                .content();
        List<String> citations = selected.stream()
                .map(this::citationText)
                .toList();
        return RagResult.builder()
                .answer(answer)
                .citations(citations)
                .build();
    }

    private List<Document> rerank(String prompt, List<Document> docs) {
        Set<String> promptTokens = tokenize(prompt);
        return docs.stream()
                .sorted((a, b) -> Double.compare(scoreDoc(promptTokens, b), scoreDoc(promptTokens, a)))
                .collect(Collectors.toList());
    }

    private double scoreDoc(Set<String> promptTokens, Document doc) {
        Set<String> docTokens = tokenize(doc.getFormattedContent());
        if (docTokens.isEmpty()) {
            return 0.0;
        }
        long overlap = promptTokens.stream().filter(docTokens::contains).count();
        return (double) overlap / docTokens.size();
    }

    private Set<String> tokenize(String text) {
        if (!StringUtils.hasText(text)) {
            return Set.of();
        }
        return Arrays.stream(text.toLowerCase(Locale.ROOT).split("[^\\p{L}\\p{Nd}]+"))
                .filter(StringUtils::hasText)
                .collect(Collectors.toSet());
    }

    private String buildContext(List<Document> docs) {
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < docs.size(); i++) {
            Document d = docs.get(i);
            sb.append("[").append(i + 1).append("] ")
                    .append(citationText(d))
                    .append("\n")
                    .append(d.getFormattedContent())
                    .append("\n\n");
        }
        return sb.toString();
    }

    private String citationText(Document d) {
        Object file = d.getMetadata().getOrDefault("file_name", "unknown");
        Object chunk = d.getMetadata().getOrDefault("chunk_index", "?");
        return "source=" + file + ", chunk=" + chunk;
    }

    @Data
    @Builder
    public static class RagResult {
        private String answer;
        private List<String> citations;
    }
}
