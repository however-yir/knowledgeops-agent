#!/usr/bin/env python3
import argparse
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path


def make_headers(args):
    headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}
    if args.bearer_token:
        headers["Authorization"] = f"Bearer {args.bearer_token}"
    elif args.api_key:
        headers["X-API-Key"] = args.api_key
    if args.tenant_id:
        headers["X-Tenant-ID"] = args.tenant_id
    return headers


def extract_citations(done_payload):
    if not isinstance(done_payload, dict):
        return []
    citations = []

    direct = done_payload.get("citations")
    if isinstance(direct, list):
        for item in direct:
            text = str(item).strip()
            if text:
                citations.append(text)

    trace = done_payload.get("trace") or []
    for step in trace:
        if not isinstance(step, dict):
            continue
        observation = step.get("observation")
        if not isinstance(observation, dict):
            continue
        values = observation.get("citations")
        if isinstance(values, list):
            for item in values:
                text = str(item).strip()
                if text:
                    citations.append(text)
    # unique + order
    seen = set()
    result = []
    for item in citations:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def stream_chat(base_url, body, headers, timeout):
    url = f"{base_url.rstrip('/')}/ai/react/chat/stream"
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")

    started = time.perf_counter()
    first_token_ms = None
    token_buffer = []
    done_payload = None
    error_message = ""

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
                if data_lines:
                    joined = "\n".join(data_lines)
                    try:
                        payload = json.loads(joined)
                    except json.JSONDecodeError:
                        payload = joined

                    if event_name == "token" and isinstance(payload, dict):
                        token = str(payload.get("token", ""))
                        if token and first_token_ms is None:
                            first_token_ms = (time.perf_counter() - started) * 1000.0
                        token_buffer.append(token)
                    elif event_name == "done":
                        if first_token_ms is None:
                            first_token_ms = (time.perf_counter() - started) * 1000.0
                        if isinstance(payload, dict):
                            done_payload = payload
                        break
                    elif event_name == "error":
                        if isinstance(payload, dict):
                            error_message = str(payload.get("message", "stream error"))
                        else:
                            error_message = str(payload)
                        break

                event_name = "message"
                data_lines = []
                continue

            # Spring WebFlux may wrap emitted SSE strings as data:event/data:data lines.
            # Support both wrapped and raw SSE formats.
            if line.startswith("data:event:"):
                event_name = line[len("data:event:"):].strip() or "message"
            elif line.startswith("data:data:"):
                data_lines.append(line[len("data:data:"):].strip())
            elif line.startswith("event:"):
                event_name = line[len("event:"):].strip() or "message"
            elif line.startswith("data:"):
                payload = line[len("data:"):].strip()
                if payload:
                    data_lines.append(payload)

    total_latency_ms = (time.perf_counter() - started) * 1000.0

    answer = ""
    if isinstance(done_payload, dict):
        answer = str(done_payload.get("answer", "") or "")
    if not answer:
        answer = "".join(token_buffer)

    if done_payload is not None and not error_message:
        status = "ok"
    else:
        status = "error"
        if not error_message and not answer:
            error_message = "stream ended without done payload"

    return {
        "status": status,
        "answer": answer,
        "error": error_message,
        "citations": extract_citations(done_payload),
        "first_token_latency_ms": round(first_token_ms, 2) if first_token_ms is not None else None,
        "total_latency_ms": round(total_latency_ms, 2),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="evaluation/dataset.json")
    parser.add_argument("--output", default="evaluation/predictions.live.json")
    parser.add_argument("--base-url", default="http://localhost:8080")
    parser.add_argument("--timeout", type=float, default=40.0)
    parser.add_argument("--limit", type=int, default=0, help="0 means all")
    parser.add_argument("--model-profile", default="balanced")
    parser.add_argument("--api-key", default=os.getenv("E2E_API_KEY", "dev-admin-key-2026"))
    parser.add_argument("--bearer-token", default="")
    parser.add_argument("--tenant-id", default="")
    args = parser.parse_args()

    dataset = json.loads(Path(args.dataset).read_text(encoding="utf-8"))
    if args.limit and args.limit > 0:
        dataset = dataset[: args.limit]

    headers = make_headers(args)

    predictions = []
    for idx, case in enumerate(dataset, start=1):
        case_id = str(case.get("id", ""))
        body = {
            "prompt": case.get("question", ""),
            "chatId": case.get("chatId", f"eval-live-{idx:03d}"),
            "modelProfile": args.model_profile,
        }

        try:
            result = stream_chat(args.base_url, body, headers, args.timeout)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, RuntimeError) as exc:
            result = {
                "status": "error",
                "answer": "",
                "error": str(exc),
                "citations": [],
                "first_token_latency_ms": None,
                "total_latency_ms": None,
            }

        prediction = {"id": case_id}
        prediction.update(result)
        predictions.append(prediction)
        print(f"[{idx}/{len(dataset)}] {case_id}: {prediction['status']}")

    out_path = Path(args.output)
    out_path.write_text(json.dumps(predictions, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"written: {out_path} ({len(predictions)} records)")


if __name__ == "__main__":
    main()
