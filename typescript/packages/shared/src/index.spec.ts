import { describe, expect, it } from "vitest";

import { fail, ok } from "./index.js";

describe("shared result helpers", () => {
  it("wraps successful payloads", () => {
    expect(ok({ id: "chat-1" })).toEqual({
      ok: 1,
      data: { id: "chat-1" }
    });
  });

  it("wraps failure messages", () => {
    expect(fail("invalid token")).toEqual({
      ok: 0,
      message: "invalid token"
    });
  });
});
