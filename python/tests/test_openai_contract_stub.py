from __future__ import annotations

import importlib.util
import json
import socket
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any


def load_contract_stub() -> Any:
    script = Path(__file__).parents[1] / "scripts" / "openai_contract_stub.py"
    spec = importlib.util.spec_from_file_location("openai_contract_stub", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_contract_stub_accepts_chunked_openai_requests() -> None:
    stub = load_contract_stub()
    server = ThreadingHTTPServer(("127.0.0.1", 0), stub.ContractStubHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    assert isinstance(port, int)
    body = b'{"messages":[{"role":"user","content":"Return JSON only"}]}'
    request = (
        b"POST /v1/chat/completions HTTP/1.1\r\n"
        b"Host: contract-model\r\n"
        b"Content-Type: application/json\r\n"
        b"Transfer-Encoding: chunked\r\n"
        b"Connection: close\r\n\r\n"
        + f"{len(body):X}\r\n".encode()
        + body
        + b"\r\n0\r\n\r\n"
    )
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=2) as client:
            client.sendall(request)
            response = b"".join(iter(lambda: client.recv(4096), b""))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert b"HTTP/1.1 200" in response
    payload = json.loads(response.split(b"\r\n\r\n", maxsplit=1)[1])
    content = payload["choices"][0]["message"]["content"]
    assert json.loads(content)["action"] == "finish"
