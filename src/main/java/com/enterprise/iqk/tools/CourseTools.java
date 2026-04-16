package com.enterprise.iqk.tools;

import cn.hutool.core.collection.CollUtil;
import cn.hutool.core.util.StrUtil;
import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.enterprise.iqk.domain.Course;
import com.enterprise.iqk.domain.CourseReservation;
import com.enterprise.iqk.domain.School;
import com.enterprise.iqk.domain.query.CourseQuery;
import com.enterprise.iqk.service.ICourseReservationService;
import com.enterprise.iqk.service.ICourseService;
import com.enterprise.iqk.service.ISchoolService;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import lombok.RequiredArgsConstructor;
import org.springframework.ai.tool.annotation.Tool;
import org.springframework.ai.tool.annotation.ToolParam;
import org.springframework.stereotype.Component;

import java.util.List;
import java.util.Set;
import java.util.function.Supplier;

@Component
@RequiredArgsConstructor
public class CourseTools {
    private static final Set<String> ALLOWED_SORT_FIELDS = Set.of("price", "duration", "edu", "id");

    private final ICourseService courseService;
    private final ISchoolService schoolService;
    private final ICourseReservationService courseReservationService;
    private final MeterRegistry meterRegistry;

    @Tool(description = "根据条件查询对应的课程，返回的是课程的列表集合")
    public List<Course> queryCourse(@ToolParam(required = false, description = "需要查询的课程的条件") CourseQuery query) {
        return instrument("query_course", () -> {
            CourseQuery safeQuery = query == null ? new CourseQuery() : query;
            QueryWrapper<Course> qw = new QueryWrapper<>();
            qw.le(safeQuery.getEdu() != null, "edu", safeQuery.getEdu());
            qw.eq(StrUtil.isNotBlank(safeQuery.getType()), "type", safeQuery.getType());

            if (CollUtil.isNotEmpty(safeQuery.getSorts())) {
                for (CourseQuery.Sort sort : safeQuery.getSorts()) {
                    if (sort == null || !ALLOWED_SORT_FIELDS.contains(sort.getField())) {
                        continue;
                    }
                    boolean isAsc = sort.getIsAsc() == null || sort.getIsAsc();
                    qw.orderBy(true, isAsc, sort.getField());
                }
            }
            return courseService.list(qw);
        });
    }

    @Tool(description = "查询所有的校区列表")
    public List<School> querySchool() {
        return instrument("query_school", schoolService::list);
    }

    @Tool(description = "新增学生的预约单记录，并且返回预约的单号")
    public String addCourseReservation(
            @ToolParam(required = true, description = "学生预约的课程名称") String course,
            @ToolParam(required = true, description = "学生预留的姓名") String studentName,
            @ToolParam(required = true, description = "学生预留的联系方式") String contactInfo,
            @ToolParam(required = true, description = "学生选择试听的校区名字") String school,
            @ToolParam(required = false, description = "学生预留的备注信息") String remark
    ) {
        return instrument("add_course_reservation", () -> {
            CourseReservation reservation = new CourseReservation();
            reservation.setCourse(course);
            reservation.setStudentName(studentName);
            reservation.setContactInfo(contactInfo);
            reservation.setSchool(school);
            reservation.setRemark(remark);
            courseReservationService.save(reservation);
            return reservation.getId().toString();
        });
    }

    private <T> T instrument(String toolName, Supplier<T> operation) {
        Timer.Sample sample = Timer.start(meterRegistry);
        try {
            T result = operation.get();
            stopTimer(sample, toolName, "success");
            return result;
        } catch (RuntimeException ex) {
            stopTimer(sample, toolName, "error");
            throw ex;
        }
    }

    private void stopTimer(Timer.Sample sample, String toolName, String status) {
        sample.stop(Timer.builder("tool.query.latency")
                .description("Latency for tool-layer query and write operations")
                .tag("tool", toolName)
                .tag("status", status)
                .publishPercentileHistogram()
                .register(meterRegistry));
    }
}
