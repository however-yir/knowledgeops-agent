package com.enterprise.iqk.config;

import com.enterprise.iqk.constants.SystemConstants;
import com.enterprise.iqk.tools.CourseTools;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.client.advisor.MessageChatMemoryAdvisor;
import org.springframework.ai.chat.client.advisor.QuestionAnswerAdvisor;
import org.springframework.ai.chat.client.advisor.SimpleLoggerAdvisor;
import org.springframework.ai.chat.memory.ChatMemory;
import org.springframework.ai.chat.prompt.ChatOptions;
import org.springframework.ai.ollama.OllamaChatModel;
import org.springframework.ai.openai.OpenAiChatModel;
import org.springframework.ai.vectorstore.SearchRequest;
import org.springframework.ai.vectorstore.VectorStore;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class CommonConfiguration {

    @Bean
    public ChatClient chatClient(OpenAiChatModel model,ChatMemory chatMemory){
        return ChatClient
                .builder(model)
                .defaultOptions(ChatOptions.builder().model("qwen-omni-turbo").build())
                .defaultAdvisors(new SimpleLoggerAdvisor())//帮我记录日志
                .defaultAdvisors(new MessageChatMemoryAdvisor(chatMemory))//增强器，MessageChatMemoryAdvisor：帮我们存储对话的上下文
                .defaultSystem("你是一个专业、友好、可靠的AI助手，请基于用户问题给出清晰、准确、简洁的回答。")
                .build();
    }

    @Bean
    public ChatClient serviceChatClient(OpenAiChatModel model,
                                        ChatMemory chatMemory,
                                        CourseTools courseTools){
        return ChatClient
                .builder(model)
                .defaultSystem(SystemConstants.CUSTOMER_SERVICE_SYSTEM)
                .defaultTools(courseTools)
                .defaultAdvisors(new SimpleLoggerAdvisor())//帮我记录日志
                .defaultAdvisors(new MessageChatMemoryAdvisor(chatMemory))//增强器，MessageChatMemoryAdvisor：帮我们存储对话的上下文
                .build();
    }

    @Bean
    public ChatClient pdfChatClient(OpenAiChatModel model,
                                        ChatMemory chatMemory,
                                    VectorStore vectorStore){
        return ChatClient
                .builder(model)
                .defaultSystem("请严格按照上下文的内容进行回答，如果上下文里面没有类似内容，就回答没匹配到数据库")
                .defaultAdvisors(new SimpleLoggerAdvisor())//帮我记录日志
                .defaultAdvisors(new MessageChatMemoryAdvisor(chatMemory))//增强器，MessageChatMemoryAdvisor：帮我们存储对话的上下文
                .defaultAdvisors(new QuestionAnswerAdvisor(vectorStore, SearchRequest.builder()
                        .topK(2)
                        .similarityThreshold(0.5)//阈值
                        .build()))
                .build();
    }

    @Bean
    public ChatMemory chatMemory(MysqlChatMemory mysqlChatMemory){
        return mysqlChatMemory;
    }

}
