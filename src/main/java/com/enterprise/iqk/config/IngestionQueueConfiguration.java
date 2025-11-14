package com.enterprise.iqk.config;

import com.enterprise.iqk.config.properties.IngestionProperties;
import lombok.RequiredArgsConstructor;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.Declarables;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@RequiredArgsConstructor
@ConditionalOnProperty(prefix = "app.ingestion", name = "queue-backend", havingValue = "rabbitmq")
public class IngestionQueueConfiguration {

    private final IngestionProperties ingestionProperties;

    @Bean
    public Declarables ingestionRabbitDeclarables() {
        IngestionProperties.Rabbit rabbit = ingestionProperties.getRabbit();
        DirectExchange mainExchange = new DirectExchange(rabbit.getExchange(), true, false);
        DirectExchange dlqExchange = new DirectExchange(rabbit.getDlqExchange(), true, false);
        Queue mainQueue = QueueBuilder.durable(rabbit.getQueue())
                .withArgument("x-dead-letter-exchange", rabbit.getDlqExchange())
                .withArgument("x-dead-letter-routing-key", rabbit.getDlqRoutingKey())
                .build();
        Queue dlqQueue = QueueBuilder.durable(rabbit.getDlqQueue()).build();

        return new Declarables(
                mainExchange,
                dlqExchange,
                mainQueue,
                dlqQueue,
                BindingBuilder.bind(mainQueue).to(mainExchange).with(rabbit.getRoutingKey()),
                BindingBuilder.bind(dlqQueue).to(dlqExchange).with(rabbit.getDlqRoutingKey())
        );
    }
}
