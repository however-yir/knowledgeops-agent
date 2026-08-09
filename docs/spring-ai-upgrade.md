# Spring AI 1.1.7 migration record

KnowledgeOps now uses the Spring AI `1.1.7` stable line with Spring Boot 3.4.5
and Java 17. The migration is checked by `mvn validate compile` and `mvn verify`
without starting Docker or a model provider.

## Applied compatibility changes

- Spring starters use the stable `spring-ai-starter-*` naming convention.
- Vector retrieval adds `spring-ai-advisors-vector-store` and builds
  `QuestionAnswerAdvisor` through its supported builder.
- `MessageChatMemoryAdvisor` uses its builder; the custom memory store now
  implements `ChatMemory#get(String)` and retains the bounded overload for
  focused unit tests.
- Conversation IDs use `ChatMemory.CONVERSATION_ID`.
- `Media` uses `org.springframework.ai.content.Media`.
- `TokenTextSplitter` uses its supported builder rather than the removed
  five-argument constructor.

The project intentionally does not jump to Spring AI 2.0 because that line is
not a stable target for this Spring Boot 3.4 application. Upgrading again
requires a separate compatibility review and a real deployed ragproof baseline
comparison.
