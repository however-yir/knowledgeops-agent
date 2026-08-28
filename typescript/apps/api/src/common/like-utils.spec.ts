import { describe, expect, it } from "vitest";

import { escapeForLike } from "./like-utils.js";

describe("escapeForLike", () => {
  it("escapes MySQL LIKE wildcards and backslashes", () => {
    expect(escapeForLike("100%_done")).toBe("100\\%\\_done");
    expect(escapeForLike("a\\b")).toBe("a\\\\b");
  });

  it("passes through empty and missing keywords", () => {
    expect(escapeForLike("")).toBe("");
    expect(escapeForLike(undefined)).toBeUndefined();
  });
});
