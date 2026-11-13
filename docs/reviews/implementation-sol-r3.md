# Sol implementation review, round 3

GPT-6.1 Sol through Codex returned CHANGES on snapshot `3cca0f20abb2983c6981af6ea24334e779ad955aa0c6204f85a0f40a61befb20`.

| ID | Severity | Finding and current correction |
| --- | --- | --- |
| S1 | should | Body-read failures escaped network handling; malformed success JSON could break kiosk state. Body-read/JSON errors now become uncertain-response errors, and kiosk results are validated before success dispatch. Five real-client/hook regressions failed before and pass after. Actual browser proof commits a tap, replaces its reply with malformed JSON, observes uncertainty and no replay. |
| S2 | should | Recovery emails linked to a missing frontend route. Login now exposes recovery request; reset page validates token/password confirmation, calls the existing endpoint, removes token from URL, and handles missing/used/expired outcomes. Twelve focused frontend tests plus actual reset/session-revocation/new-login browser proof pass. Proxy prevents token access logging/referrer leakage. Real SMTP delivery is still deferred. |
| S3 | should | Moving password hash to users exposed it through table-wide SQL grants and bypassed password-service session revocation. Role bootstrap now revokes old table and column grants, grants only visible user columns, and browser/generated SQL projects them. Tests deny hash read/update/insert/whole-row JSON and preserve ordinary SQL; actual reprovisioned candidate denies hash access. Pending email payloads with recovery links are also hidden credential material. |
| S4 | nit | Canvas task publishes domain data before the library marks its job terminal, leaving status stale. Accepted because live status matters: a small PostgreSQL trigger bridges Canvas library job status commits to staff invalidations. No job tables or custom scheduler added. Actual library-worker/PostgreSQL regression verifies final terminal invalidation. |

Reviewer independently checked all 257 source hashes, both diff hashes, 41 Python parses, frontend failure reproductions and source call paths. It did not rerun full suites or runtime checks. No score or usage returned. No source changed by reviewer. Corrected behavior remains unapproved pending focused follow-up.
