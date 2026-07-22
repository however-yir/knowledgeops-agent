"""Deterministic, local OpenAI-compatible provider for the cross-runtime contract stack."""

from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


class ContractStubHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self.send_json({"status": "UP"})
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        try:
            payload = json.loads(self.read_request_body() or b"{}")
        except (ValueError, json.JSONDecodeError):
            self.send_json({"error": {"message": "invalid JSON"}}, HTTPStatus.BAD_REQUEST)
            return
        if self.path.endswith("/chat/completions"):
            self.chat_completion(payload)
            return
        if self.path.endswith("/embeddings"):
            self.embedding(payload)
            return
        if self.path.endswith("/rerank"):
            self.send_json({"scores": [1.0 for _ in payload.get("documents", [])]})
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def read_request_body(self) -> bytes:
        if self.headers.get("Transfer-Encoding", "").lower() != "chunked":
            return self.rfile.read(int(self.headers.get("Content-Length", "0")))

        chunks: list[bytes] = []
        while True:
            size_line = self.rfile.readline().strip()
            chunk_size = int(size_line.split(b";", maxsplit=1)[0], 16)
            if chunk_size == 0:
                while self.rfile.readline().strip():
                    pass
                return b"".join(chunks)
            chunks.append(self.rfile.read(chunk_size))
            if self.rfile.read(2) != b"\r\n":
                raise ValueError("invalid chunk terminator")

    def chat_completion(self, payload: dict[str, Any]) -> None:
        messages = payload.get("messages", [])
        prompt = "\n".join(str(message.get("content", "")) for message in messages if isinstance(message, dict))
        if "contract provider failure" in prompt:
            self.send_json({"error": {"message": "contract provider failure"}}, HTTPStatus.SERVICE_UNAVAILABLE)
            return
        answer = (
            '{"thought":"contract plan","action":"finish","action_input":{},"answer":"Contract answer"}'
            if "Return JSON only" in prompt
            else "Contract answer"
        )
        if payload.get("stream"):
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Connection", "close")
            self.end_headers()
            for chunk in (answer,):
                event = {"choices": [{"index": 0, "delta": {"content": chunk}, "finish_reason": None}]}
                self.wfile.write(f"data: {json.dumps(event)}\n\n".encode())
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
            self.close_connection = True
            return
        self.send_json(
            {
                "id": "contract-completion",
                "object": "chat.completion",
                "created": 0,
                "model": str(payload.get("model") or "contract-model"),
                "choices": [{"index": 0, "message": {"role": "assistant", "content": answer}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
            }
        )

    def embedding(self, payload: dict[str, Any]) -> None:
        inputs = payload.get("input", [])
        values = inputs if isinstance(inputs, list) else [inputs]
        self.send_json(
            {
                "object": "list",
                "data": [{"object": "embedding", "index": index, "embedding": [0.01] * 1024} for index, _ in enumerate(values)],
                "model": str(payload.get("model") or "contract-embedding"),
                "usage": {"prompt_tokens": len(values), "total_tokens": len(values)},
            }
        )

    def send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        encoded = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, _format: str, *_args: object) -> None:
        return


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8000), ContractStubHandler).serve_forever()
