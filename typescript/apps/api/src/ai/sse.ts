import type { FastifyReply, FastifyRequest } from "fastify";

export interface SseEvent {
  event: "trace" | "token" | "done" | "error";
  data: unknown;
}

export async function sendSse(
  request: FastifyRequest,
  reply: FastifyReply,
  stream: (signal: AbortSignal) => AsyncIterable<SseEvent>
): Promise<void> {
  const controller = new AbortController();
  const abort = () => controller.abort(new DOMException("client disconnected", "AbortError"));
  request.raw.once("aborted", abort);
  reply.raw.once("close", abort);
  reply.hijack();
  reply.raw.writeHead(200, {
    "content-type": "text/event-stream; charset=utf-8",
    "cache-control": "no-cache, no-transform",
    "connection": "keep-alive",
    "x-accel-buffering": "no"
  });
  reply.raw.flushHeaders?.();
  try {
    for await (const event of stream(controller.signal)) {
      if (controller.signal.aborted || reply.raw.destroyed) break;
      const writable = reply.raw.write(formatSse(event));
      if (!writable) await onceDrain(reply.raw, controller.signal);
    }
  } catch (error) {
    if (!controller.signal.aborted && !reply.raw.destroyed) {
      reply.raw.write(formatSse({ event: "error", data: { message: error instanceof Error ? error.message : String(error) } }));
    }
  } finally {
    request.raw.off("aborted", abort);
    reply.raw.off("close", abort);
    if (!reply.raw.destroyed && !reply.raw.writableEnded) reply.raw.end();
  }
}

export function formatSse(event: SseEvent): string {
  const data = JSON.stringify(event.data).replace(/\n/g, "\\n");
  return `event: ${event.event}\ndata: ${data}\n\n`;
}

function onceDrain(stream: NodeJS.WritableStream, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const onDrain = () => finish(resolve);
    const onAbort = () => finish(() => reject(signal.reason));
    const finish = (callback: () => void) => {
      stream.off("drain", onDrain);
      signal.removeEventListener("abort", onAbort);
      callback();
    };
    stream.once("drain", onDrain);
    signal.addEventListener("abort", onAbort, { once: true });
  });
}
