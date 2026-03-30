package com.demo.ai.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.demo.ai.domain.Conversation;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface ConversationMapper extends BaseMapper<Conversation> {
}
