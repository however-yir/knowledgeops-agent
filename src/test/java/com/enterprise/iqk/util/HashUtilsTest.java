package com.enterprise.iqk.util;

import org.junit.jupiter.api.Test;

import java.io.ByteArrayInputStream;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;

class HashUtilsTest {

    @Test
    void shouldReturnStableHash() {
        String hash1 = HashUtils.sha256Hex("abc");
        String hash2 = HashUtils.sha256Hex("abc");
        String hash3 = HashUtils.sha256Hex("abcd");
        assertEquals(hash1, hash2);
        assertNotEquals(hash1, hash3);
    }

    @Test
    void shouldHashInputStreamWithSameResultAsString() {
        String expected = HashUtils.sha256Hex("hello");
        String actual = HashUtils.sha256Hex(new ByteArrayInputStream("hello".getBytes()));
        assertEquals(expected, actual);
    }
}
