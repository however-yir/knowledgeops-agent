package com.enterprise.iqk.service.impl;

import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import com.enterprise.iqk.domain.CourseReservation;
import com.enterprise.iqk.mapper.CourseReservationMapper;
import com.enterprise.iqk.service.ICourseReservationService;
import org.springframework.stereotype.Service;

@Service
public class CourseReservationServiceImpl extends ServiceImpl<CourseReservationMapper, CourseReservation> implements ICourseReservationService {

}