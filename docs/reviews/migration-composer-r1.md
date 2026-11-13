# Migration preflight, Composer round 1

Snapshot f274d4c8e1fdb09b2a06f771790b3d1bef6f4f61b5fc2f3cf9ec0aceb8cc4bda. Task suffix sfl-migration-composer-20261110-r1. Composer2.5 additional review.

## VERDICT: APPROVE

Additional Composer review for snapshot `f274d4c8e1fdb09b2a06f771790b3d1bef6f4f61b5fc2f3cf9ec0aceb8cc4bda` (`reviews/migration-preflight-round-1`). No blocker or should findings in the intended read-only export → offline inspect workflow.

### Independent checks (not re-running full image/Compose proof)

| Check | Result |
| --- | --- |
| `source/backend/app/legacy_preflight.py` and `tests/test_legacy_preflight.py` SHA-256 vs `manifest.json` | Match |
| `pytest tests/test_legacy_preflight.py` on snapshot tree (host Python 3.14, no venv) | 23 passed; 1 failed (`import psycopg` missing); 1 error (`@pytest.mark.postgres` skipped without DB) |
| Supplied `focused-tests.log` | 25/25 (consistent with container deps) |
| Supplied `final-container-tests.log` | 214 passed / 31.35s |
| Trace of `legacy_preflight.py`, `zund-live-comparison.md`, `legacy-schema.sql` vs `COLUMNS` | Aligns with stated scope |

Host pytest gaps are environmental; they do not contradict primary container evidence.

### Operator usability and evidence

- **Two-command CLI** is clear: export needs an explicit `--source-dsn-env` (not `DATABASE_URL` by default); inspect never connects. Exit codes 0 / 2 / 1 match docs and tests.
- **`zund-live-comparison.md`** matches behavior: eight categories, Policies quiz vs assignment `2839627`, aggregate anomalies, `ready_for_import` / `apply_supported` always false, no apply path. Usage examples include `--canvas-mappings` for the intended inspect path.
- **Without `--canvas-mappings`**, non-null legacy `canvas_id` values correctly yield `unverified_canvas_assignment_mapping` blockers (tested); this is strict, not silent guessing.
- **Reports stay aggregate**: tests and code paths keep names, emails, IDs, media paths, and hash material out of inspect JSON; assignment proposals only expose names already in `zund-canvas-assignments.json`.

### Privacy and file safety

- Export: DB-enforced read-only + `REPEATABLE READ READ ONLY`, fixed five-table `public."…"` projections, credential **labels only**, `ROLLBACK`, DSN/rows not echoed on failure.
- Outputs: `O_CREAT \| O_EXCL` and mode `0600`, symlink/overwrite refused (`private_json` tests).
- Validate step rejects `password` and other undeclared columns before inspection mutates nothing.

### Schema vs fixed projections (gaps, as designed)

Captured DDL (`legacy-schema.sql`) vs export:

| In live schema | In export | Assessment |
| --- | --- | --- |
| `users_spaceuser.last_login`, groups/permissions M2M, auth/session/Celery tables | Omitted | Consistent with “five domain tables, no sessions/jobs” |
| Five domain tables + `password` (for label CASE only) | Projected columns only | Matches proof fixture and tests |
| Nullable `forgot_to_signout`, optional `canvas_id` | Included | Handled (`null` → normalization counts) |

`user_url` is exported in the private JSON (appropriate for a future migration backup) but not surfaced in inspect aggregates beyond row counts—reasonable for this phase.

### Findings (non-gating)

| ID | Severity | Path | Evidence | Minimal fix |
| --- | --- | --- | --- | --- |
| C1 | nit | `source/docs/research/zund-live-comparison.md` (limitations / export omit list) | Schema has `last_login`; export omits it by design but docs only call out hashes/sessions/media | One sentence listing `last_login` and permission M2M as intentional omissions |
| C2 | nit | `source/backend/tests/test_legacy_preflight.py:275` | Offline CLI test imports `psycopg` solely to monkeypatch; fails on bare host without backend deps | Lazy-import inside test or skip when `psycopg` missing (container proof already covers) |
| C3 | nit | `source/backend/app/legacy_preflight.py:452-454` | Successful `export` stdout is a small JSON blob with no `--output` path reminder | Optional one-line hint in stdout (operators already pass `--output`) |

No broken callers in snapshot: module avoids app startup; scope excludes API/UI/schema changes.

### Score

**9/10** — Focused tool, strong privacy/file-safety boundaries, and tests match stated migration-prep intent; minor doc/test ergonomics only (C1–C3).
