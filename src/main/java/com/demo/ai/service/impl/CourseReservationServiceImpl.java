package com.demo.ai.service.impl;

import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import com.demo.ai.domain.CourseReservation;
import com.demo.ai.mapper.CourseReservationMapper;
import com.demo.ai.service.ICourseReservationService;
import org.springframework.stereotype.Service;

@Service
public class CourseReservationServiceImpl extends ServiceImpl<CourseReservationMapper, CourseReservation> implements ICourseReservationService {

}