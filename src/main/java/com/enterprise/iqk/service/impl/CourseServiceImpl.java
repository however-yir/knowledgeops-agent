package com.enterprise.iqk.service.impl;

import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import com.enterprise.iqk.domain.Course;
import com.enterprise.iqk.mapper.CourseMapper;
import com.enterprise.iqk.service.ICourseService;
import org.springframework.stereotype.Service;

@Service
public class CourseServiceImpl extends ServiceImpl<CourseMapper, Course> implements ICourseService {

}