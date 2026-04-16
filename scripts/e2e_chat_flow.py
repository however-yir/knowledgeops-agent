#!/usr/bin/env python3
import argparse
import json
import os
import time
import urllib.error
import urllib.request


def make_headers(args, accept_json=True):
    headers = {"Content-Type": "application/json"}
    if accept_json:
        headers["Accept"] = "application/json"
    if args.bearer_token:
        headers["Authorization"] = f"Bearer {args.bearer_token}"
    elif args.api_key:
        headers["X-API-Key"] = args.api_key
    if args.tenant_id:
        headers["X-Tenant-ID"] = args.tenant_id
    return headers


def http_json(url, body=None, headers=None, timeout=20.0):
    data = None if body is None else json.dumps(body).encode("utf-8")
    method = "GET" if body is None else "POST"
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        text = resp.read().decode("utf-8", errors="replace")
        return resp.status, json.loads(text) if text else {}


def stream_sse(url, body, headers, timeout=40.0):
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")

    token_seen = False
    done_payload = None
    error_message = ""

    def consume_event(event, data):
        nonlocal token_seen, done_payload, error_message
        if not data:
            return False
        joined = "\n".join(data)
        try:
            payload = json.loads(joined)
        except json.JSONDecodeError:
            payload = {"raw": joined}

        if event == "token":
            token = str(payload.get("token", ""))
            if token:
                token_seen = True
        elif event == "done":
            if isinstance(payload, dict):
                done_payload = payload
            return True
        elif event == "error":
            error_message = str(payload.get("message", "stream error"))
            return True
        return False

    with urllib.request.urlopen(req, timeout=timeout) as resp:
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status}")

        event_name = "message"
        data_lines = []

        while True:
            raw = resp.readline()
            if not raw:
                break
            line = raw.decode("utf-8", errors="replace").rstrip("\r\n")

            if line == "":
                if consume_event(event_name, data_lines):
                    break

                event_name = "message"
                data_lines = []
                continue

            # Spring WebFlux may wrap our preformatted SSE payload as:
            # data:event: token
            # data:data: {"token":"..."}
            # Keep compatibility with both wrapped and raw SSE layouts.
            if line.startswith("data:event:"):
                event_name = line[len("data:event:"):].strip() or "message"
            elif line.startswith("data:data:"):
                data_lines.append(line[len("data:data:"):].strip())
            elif line.startswith("event:"):
                event_name = line[len("event:"):].strip() or "message"
            elif line.startswith("data:"):
                payload = line[len("data:"):].strip()
                # ignore empty heartbeat "data:" lines
                if payload:
                    data_lines.append(payload)

        if done_payload is None and not error_message:
            consume_event(event_name, data_lines)

    return token_seen, done_payload, error_message


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8080")
    parser.add_argument("--api-key", default=os.getenv("E2E_API_KEY", "dev-admin-key-2026"))
    parser.add_argument("--bearer-token", default="")
    parser.add_argument("--tenant-id", default="")
    parser.add_argument("--model-profile", default="balanced")
    args = parser.parse_args()

    started = time.perf_counter()

    health_url = f"{args.base_url.rstrip('/')}/actuator/health"
    status, payload = http_json(health_url, headers=make_headers(args))
    if status != 200 or payload.get("status") != "UP":
        raise SystemExit("health check failed")
    print("health ok")

    chat_url = f"{args.base_url.rstrip('/')}/ai/react/chat"
    chat_body = {
        "chatId": f"e2e-chat-{int(time.time())}",
        "prompt": "请返回一句可执行建议，并保持简洁。",
        "modelProfile": args.model_profile,
    }
    status, payload = http_json(chat_url, body=chat_body, headers=make_headers(args), timeout=40.0)
    if status != 200:
        raise SystemExit(f"chat endpoint failed: HTTP {status}")
    if payload.get("ok") != 1:
        raise SystemExit("chat response ok != 1")
    if not str(payload.get("answer", "")).strip():
        raise SystemExit("chat answer is empty")
    print("chat endpoint ok")

    stream_url = f"{args.base_url.rstrip('/')}/ai/react/chat/stream"
    stream_headers = make_headers(args, accept_json=False)
    stream_headers["Accept"] = "text/event-stream"
    token_seen, done_payload, error_message = stream_sse(stream_url, chat_body, stream_headers, timeout=60.0)

    if error_message:
        raise SystemExit(f"stream endpoint returned error: {error_message}")
    if done_payload is None:
        raise SystemExit("stream endpoint missing done event")
    if done_payload.get("ok") != 1:
        raise SystemExit("stream done payload ok != 1")
    if not token_seen and not str(done_payload.get("answer", "")).strip():
        raise SystemExit("stream endpoint produced neither token nor answer")

    elapsed = (time.perf_counter() - started) * 1000.0
    print(f"stream endpoint ok (token_seen={token_seen})")
    print(f"e2e chat flow success in {elapsed:.2f} ms")


if __name__ == "__main__":
    try:
        main()
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, RuntimeError) as exc:
        raise SystemExit(f"e2e chat flow failed: {exc}")
