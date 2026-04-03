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

function authHeaders() {
  return TOKEN
    ? { Authorization: `Bearer ${TOKEN}`, 'Content-Type': 'application/json' }
    : { 'Content-Type': 'application/json' };
}

export default function () {
  const chatBody = JSON.stringify({
    message: '请基于课程知识库回答：Java课程适合哪些基础阶段？',
    conversationId: `k6-${__VU}-${__ITER}`,
  });
  const chatRes = http.post(`${BASE}/chat`, chatBody, { headers: authHeaders() });
  check(chatRes, {
    'chat status 2xx': (r) => r.status >= 200 && r.status < 300,
  });

  const ingestionBody = JSON.stringify({
    text: `k6 sample knowledge chunk ${__VU}-${__ITER}`,
    source: 'k6-load-test',
  });
  const ingestionRes = http.post(`${BASE}/ingestion/text`, ingestionBody, { headers: authHeaders() });
  check(ingestionRes, {
    'ingestion accepted': (r) => r.status === 200 || r.status === 202,
  });

  sleep(1);
}
