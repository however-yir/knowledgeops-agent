package com.enterprise.iqk.controller;

import com.enterprise.iqk.domain.vo.Result;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.server.ResponseStatusException;

@Slf4j
@RestControllerAdvice
public class GlobalExceptionHandler {

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<Result> handleBadRequest(IllegalArgumentException e) {
        return ResponseEntity.badRequest().body(Result.fail(e.getMessage()));
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<Result> handleInternal(Exception e) {
        log.error("Unhandled exception", e);
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(Result.fail("internal server error"));
    }

    @ExceptionHandler(ResponseStatusException.class)
    public ResponseEntity<Result> handleStatusException(ResponseStatusException e) {
        return ResponseEntity.status(e.getStatusCode())
                .body(Result.fail(e.getReason() == null ? "request failed" : e.getReason()));
    }
}
