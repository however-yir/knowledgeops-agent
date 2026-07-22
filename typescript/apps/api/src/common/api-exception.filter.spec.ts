import { NotFoundException, type ArgumentsHost } from "@nestjs/common";
import { describe, expect, it, vi } from "vitest";

import { ApiExceptionFilter } from "./api-exception.filter.js";

describe("ApiExceptionFilter", () => {
  it("uses the Java Result.fail contract for controller exceptions", () => {
    const header = vi.fn();
    const send = vi.fn();
    const status = vi.fn(() => ({ send }));
    const host = {
      switchToHttp: () => ({
        getRequest: () => ({ headers: {} }),
        getResponse: () => ({ header, status })
      })
    } as ArgumentsHost;

    new ApiExceptionFilter().catch(new NotFoundException("job not found"), host);

    expect(status).toHaveBeenCalledWith(404);
    expect(send).toHaveBeenCalledWith({
      ok: 0,
      msg: "job not found",
      code: "REQUEST_FAILED",
      traceId: null,
      data: null
    });
    expect(header).toHaveBeenCalledWith("X-Trace-ID", expect.any(String));
  });
});
