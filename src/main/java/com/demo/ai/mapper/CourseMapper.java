package com.demo.ai.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.demo.ai.domain.Course;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface CourseMapper extends BaseMapper<Course> {
}
