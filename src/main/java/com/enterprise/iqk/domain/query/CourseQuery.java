package com.enterprise.iqk.domain.query;

import lombok.Data;
import org.springframework.ai.tool.annotation.ToolParam;

import java.util.List;

@Data
public class CourseQuery {

    @ToolParam(required = false,description = "课程要求的学历：0-无，1-初中，2-高中，3-大专，4-本科以上")
    private Integer edu;
    @ToolParam(required = false,description = "课程的类型：包括编程、设计、自媒体、其他")
    private String type;
    @ToolParam(required = false,description = "需要排序的字段的集合")
    private List<Sort> sorts;

    @Data
    public static class Sort{
        //字段名
        @ToolParam(required = false,description = "需要排序的字段，比如price价格、或者duration天数")
        private String field;
        //是否升序
        @ToolParam(required = false,description = "是否按照升序排序，true-升序，false-降序")
        private Boolean isAsc;
    }
}
