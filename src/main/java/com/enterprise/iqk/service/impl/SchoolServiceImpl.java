package com.enterprise.iqk.service.impl;

import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import com.enterprise.iqk.domain.School;
import com.enterprise.iqk.mapper.SchoolMapper;
import com.enterprise.iqk.service.ISchoolService;
import org.springframework.stereotype.Service;

@Service
public class SchoolServiceImpl extends ServiceImpl<SchoolMapper, School> implements ISchoolService {

}