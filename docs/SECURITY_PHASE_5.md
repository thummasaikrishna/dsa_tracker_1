# Security Phase 5 — Audit logging and abuse regression matrix

Audit records are security events, not a request archive. They retain a bounded
event type, timestamp, authenticated user when available, IP, user agent, path,
method, and allow-listed scalar metadata. Request bodies, passwords, JWTs,
authorization headers, API keys, and provider credentials are never recorded.

| Scenario | Expected secure behavior | Coverage | Result |
| --- | --- | --- | --- |
| Brute-force login | Scoped authentication throttle returns safe 429 | `test_security_auth`, `test_security_phase5` | Pass |
| JWT replay after logout | Blacklisted refresh token is rejected | `test_security_auth`, `test_security_phase5` | Pass |
| JWT replay after password change | Access and refresh tokens are revoked | `test_security_auth` | Pass |
| Blacklisted refresh reuse | Safe 401 and refresh-failure audit event | `test_security_phase5` | Pass |
| Student to admin escalation | Admin API returns centralized 403 | `test_phase2_rbac`, `test_security_phase5` | Pass |
| IDOR against another student | Foreign assignment returns 404; admin retains access | `test_phase2_rbac`, `test_security_phase5` | Pass |
| Removed-account access | Authentication fails and audit event is written | `test_security_auth`, `test_security_phase5` | Pass |
| Code execution abuse | Per-user throttle prevents sandbox call and audits event | `test_security_rate_limiting`, `test_security_phase5` | Pass |
| Submission spam | Per-user submission throttle prevents judging/persistence | `test_security_rate_limiting` | Pass |
| AI generation abuse | Admin-only endpoint is per-user throttled before provider work | `test_security_rate_limiting` | Pass |
| Oversized payload | Serializer limits return centralized validation error | `test_security_validation` | Pass |
| Malformed JSON | Centralized parse error; validation event is audited | `test_security_validation`, `test_security_phase5` | Pass |
| Query/filter abuse | Invalid filter, ordering, and pagination return safe 400 | `test_security_validation`, `test_security_phase5` | Pass |
| Method abuse | Unsupported methods return centralized 405 | `test_security_validation` | Pass |
| Provider error leakage | Provider details are replaced with a generic 503 | `test_security_validation` | Pass |
| Unexpected exception leakage | Generic 500 has no internal path or stack trace | `test_security_validation` | Pass |
| Audit-log injection | Control characters are normalized; metadata is bounded/allow-listed | `test_security_phase5` | Pass |
| Audit-log data leakage | Credential-bearing fields are never stored | `test_security_phase5` | Pass |

The matrix covers only the local DSA Tracker application and its test doubles;
it does not direct testing against external systems.
