// k6 load test for qiko-core. Run against a deployed environment:
//   BASE_URL=https://preprod.qiko.ai k6 run smoke.js
// Thresholds encode the service level objectives; the run fails if they are breached.
import http from "k6/http";
import { check, sleep } from "k6";

export const options = {
  scenarios: {
    steady: { executor: "ramping-vus", startVUs: 0,
      stages: [{ duration: "30s", target: 50 }, { duration: "2m", target: 50 }, { duration: "30s", target: 0 }] },
  },
  thresholds: {
    http_req_failed: ["rate<0.01"],        // <1% errors
    http_req_duration: ["p(95)<800"],      // p95 under 800ms
  },
};

const BASE = __ENV.BASE_URL || "http://localhost:8000";

export default function () {
  const res = http.get(`${BASE}/health`);
  check(res, { "status is 200": (r) => r.status === 200 });
  sleep(1);
}
