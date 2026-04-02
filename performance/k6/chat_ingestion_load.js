import http from "k6/http";
import { check, sleep } from "k6";

export const options = {
  scenarios: {
    chat_and_rag: {
      executor: "ramping-vus",
      startVUs: 5,
      stages: [
        { duration: "1m", target: 20 },
        { duration: "3m", target: 50 },
        { duration: "1m", target: 0 },
      ],
      gracefulRampDown: "30s",
    },
  },
  thresholds: {
    http_req_duration: ["p(95)<1500"],
    http_req_failed: ["rate<0.02"],
  },
};

const BASE = __ENV.BASE_URL || "http://localhost:8080";

export default function () {
  const chatId = `load-${__VU}-${__ITER}`;
  const chatRes = http.get(`${BASE}/ai/chat?prompt=你好&chatId=${chatId}`);
  check(chatRes, { "chat status 200": (r) => r.status === 200 });

  const ragRes = http.get(
    `${BASE}/ai/pdf/chat?prompt=总结该知识库重点并给出引用&chatId=${chatId}`,
  );
  check(ragRes, { "rag status 200": (r) => r.status === 200 });
  sleep(0.3);
}
