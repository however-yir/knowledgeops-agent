package com.enterprise.iqk.domain.vo;

import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@NoArgsConstructor
public class Result {
    private Integer ok;
    private String msg;
    private String code;
    private String traceId;
    private Object data;

    private Result(Integer ok, String msg) {
        this.ok = ok;
        this.msg = msg;
    }

    public static Result ok() {
        return new Result(1, "ok");
    }

    public static Result fail(String msg) {
        Result result = new Result(0, msg);
        result.setCode("REQUEST_FAILED");
        return result;
    }
}
