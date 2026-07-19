# SLOs and pre-launch hardening checklist (SCRUM-17)

## Service level objectives
Enforced by `loadtest/smoke.js` thresholds (the run fails if breached):
- Availability: error rate < 1% under 50 concurrent users (`http_req_failed: rate<0.01`).
- Latency: p95 request duration < 800 ms (`http_req_duration: p(95)<800`).

Targets to monitor (not yet enforced as a k6 threshold):
- Latency: p99 request duration < 1500 ms.
- Workers: no task backlog growth under steady load (arq queue depth stable).

## Load test
- `BASE_URL=https://preprod.qiko.ai k6 run loadtest/smoke.js` (run against preprod, then live
  pre-cutover). `BASE_URL` defaults to `http://localhost:8000` for a local run.
- The scenario ramps to 50 VUs and holds for 2 minutes. Extend scenarios per endpoint (auth, chat,
  ingest) before go-live.

## OWASP review (maps to delivered work)
- [x] A01 Broken access control: central tenant scoping (tenancy.py), RBAC guards (identity), tenant-scoped storage keys.
- [x] A02 Crypto failures: PBKDF2 password hashing, httpOnly+Secure+SameSite cookies, tokens never in localStorage.
- [x] A03 Injection: SQLAlchemy parameterised queries; Pydantic-validated tool args.
- [x] A05 Misconfig: security headers, strict CORS, request-size cap (hardening middleware).
- [x] A07 Auth failures: 2FA (TOTP), single-session revocation (sid), rate limiting.
- [x] A09 Logging: structured JSON logs with request_id + tenant correlation.
- [x] Webhooks: inbound signatures verified + idempotency (channels).
- [ ] Run a full OWASP ASVS pass + dependency scan in CI before cutover (SCRUM-16 gate).
