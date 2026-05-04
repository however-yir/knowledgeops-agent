package com.enterprise.iqk.memory;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

import java.util.List;

@Mapper
public interface MemoryEventMapper extends BaseMapper<MemoryEventRecord> {

    @Select("SELECT * FROM memory_event WHERE memory_id = #{memoryId} ORDER BY created_at DESC")
    List<MemoryEventRecord> findByMemoryId(@Param("memoryId") String memoryId);
}
