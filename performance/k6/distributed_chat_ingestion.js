import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  vus: 50,
  duration: '3m',
  thresholds: {
    http_req_duration: ['p(95)<1200'],
    http_req_failed: ['rate<0.02'],
  },
};

const BASE = __ENV.BASE_URL || 'http://localhost:8080';
const TOKEN = __ENV.BEARER_TOKEN || '';

function authHeaders(extra = {}) {
  return TOKEN
    ? { Authorization: `Bearer ${TOKEN}`, ...extra }
    : { ...extra };
}

export default function () {
  const chatId = `k6-${__VU}-${__ITER}`;
  const chatRes = http.get(
    `${BASE}/ai/chat?prompt=${encodeURIComponent('请基于课程知识库回答：Java课程适合哪些基础阶段？')}&chatId=${chatId}`,
    { headers: authHeaders() },
  );
  check(chatRes, {
    'chat status 200': (r) => r.status === 200,
  });

  const uploadBody = {
    file: http.file('%PDF-1.4\n%k6 synthetic pdf bytes\n', `${chatId}.pdf`, 'application/pdf'),
  };
  const ingestionRes = http.post(`${BASE}/ingestion/upload/${chatId}`, uploadBody, {
    headers: authHeaders({ 'X-Idempotency-Key': `idem-${chatId}` }),
  });
  check(ingestionRes, {
    'ingestion accepted': (r) => r.status === 200 || r.status === 202,
  });

  sleep(1);
}
