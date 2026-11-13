# SFL Sign In 2.0

A local Charlotte Super Fab Lab replacement candidate: pnpm/Vite/React, TanStack Router/Query, the exact shadcn preset `b2BpPb196`, FastAPI/SQLModel/PostgreSQL, private S3-compatible storage and Procrastinate background jobs.

Nothing is deployed to Zund. The user's [feedback revision 3](docs/feedback-revision-3.md), items 1–17, overrides earlier proposals. Commit `bb81f37` is the previously approved local baseline; its review does not approve these changes. Final architecture/schema approval remains the user's.

Start with the [status report](docs/status-report.md), [old repository schema](docs/research/legacy-schema.md), [new schema](docs/schema-proposal.md), [architecture choices](docs/architecture-options.md), [API contract](docs/api-contract.md) and [discussion list](docs/discussion-list.md). The primary-owned [verification log](docs/verification-log.md) and [review ledger](docs/reviews/ledger.md) record final evidence.

## What is implemented

- One internal kiosk, existing keyholder rules, anonymous occupancy/photos and binary training badges. The six original PNGs and full-name tooltips replace training tiers.
- A custom React/shadcn admin, not Django admin, Refine or React Admin. Forms are compact and vertical; audit records use human labels/links. Lists default to 100 rows, capped at 1000.
- One nullable staff role per user: operator, admin or superadmin. Physical `space_level` 0–3 remains separate. Admin can read SQL; superadmin can preview/commit supported writes and manage stored objects.
- Canvas evidence and manual awards share `trainings`; cached source ownership resolves through one external identity. No training levels, definition slug/description, `user_roles`, `canvas_results` or certifications table remains.
- Computed visit duration, consistent charts/CSV and America/New_York date boundaries with DST. Each timestamp stores one instant.

User-entered email must be `charlotte.edu` or `uncc.edu`, case-insensitively; aliases are canonicalized once. Synthetic seeds use `800000001` for superadmin, `800000002` for admin and `800000003` for operator. A demo password must be supplied at runtime; no production password is seeded.

## Start a separate local candidate

Requirements: Docker Compose, Python 3 and pnpm 10.33.0. Copy `.env.example` to an ignored `.env.beta`, choose `APP_PORT`, and supply local database/object-store passwords. Use the configured `APP_HOST`, since origins include host and port.

```sh
pnpm compose --env-file .env.beta up --build -d db minio
pnpm compose --env-file .env.beta run --rm api python -m app.cli init-db
pnpm compose --env-file .env.beta run --rm api python -m app.cli init-storage
pnpm compose --env-file .env.beta run --rm -it api python -m app.cli bootstrap-superadmin \
  --identifier YOUR_ID --first-name YOUR_FIRST_NAME --last-name YOUR_LAST_NAME --email YOUR_UNIVERSITY_EMAIL
pnpm compose --env-file .env.beta up --build -d
```

Bootstrap prompts for a password unless its explicit password environment variable is supplied. For an empty synthetic candidate, `seed-demo` is an alternative to bootstrap and also requires a runtime password. It refuses a nonempty users table. `init-db` initializes a fresh schema and the library jobs schema; it is not a production importer or an upgrade mechanism.

Always use the helper. Changing `APP_PORT` in a copied env file selects another Compose project, network, database/object volumes and session cookie name. DB/S3 ports remain internal; loopback binding is the default. No cloudflared, Adminer or automatic deployment job is included. [Deployment preparation](docs/deployment-preparation.md) covers later runner work.

## Hot reload

The new isolated feedback preview uses port **8099**. The previous synthetic demo on **8098** is preserved. Use a separate env file with `APP_PORT=8099`, then initialize that fresh instance as above and start its Vite frontend:

```sh
pnpm compose --env-file .env.feedback --dev up --build -d
```

`--dev` adds `compose.dev.yaml`, mounts frontend source and uses the development build target. Vite serves the selected app port and proxies REST, WebSockets and media to that instance's API. This is a local preview, not a Zund deployment.

## SQL and storage

Monaco and its workers/assets are bundled locally. SELECT/EXPLAIN reads run immediately, without a mode dropdown or write warning. Supported superadmin DML runs in a real held transaction and returns before/after changes; separate **Commit** and **Roll back** actions end that exact transaction without rerunning SQL. Previews expire after 90 seconds, with one per session and two globally. DDL, write joins, UPSERT and other unsupported preview forms are rejected. [Backend limits](backend/docs/implementation-status.md) explain the restricted SQL logins, row/time limits and protected account fields.

`/admin/storage` is the in-app superadmin object browser for the configured private S3 bucket. It lists/uploads/downloads/deletes objects, links referenced avatars and blocks their deletion. It does not redirect to vendor login or expose S3 credentials. API uploads/downloads are bounded at 5 MiB; production nginx permits 6 MiB multipart requests. The storage service remains S3-compatible MinIO; no replacement was selected.

## Canvas and printing

Training definitions select a cached Canvas quiz title backed by its real assignment ID and optional passing score. One paginated assignment-submissions path supplies all trainings, including classic/external-tool catalog choices. Submission ID/attempt, configuration fingerprints and successful checkpoints are retained. The default sync interval is hourly, `CANVAS_SYNC_INTERVAL_SECONDS=3600`; Procrastinate's maintenance tick dispatches due work.

Authorized real reads verified course 231237, reported Teacher access, 26 catalog assignments and submission ID/attempt fields. After correcting the omitted historical roster enrollment states, the authorized full read-only sync succeeded with 2503 cached people, 14796 training rows and six training types. Unresolved submission owners are counted/skipped safely. SMTP is explicitly disabled for this preview, so no real email was sent.

The [USB agent](devices/printer/README.md) receives live labels after attendance commits/responds. Offline/busy labels drop; lost acknowledgment means unknown output; reconnect never replays. Its wheel contains the six unchanged original PNGs and renders full names without tiers at 1109×696. Physical USB printing has not been tested.

## Checks

```sh
pnpm install --frozen-lockfile
pnpm typecheck
pnpm lint
pnpm test
pnpm build
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.lock
backend/.venv/bin/pip install --no-deps -e backend -e devices/printer
TEST_DATABASE_URL=YOUR_DISPOSABLE_POSTGRES_URL DATABASE_URL=YOUR_DISPOSABLE_POSTGRES_URL \
  PUBLIC_ORIGIN=http://testserver backend/.venv/bin/python -m pytest backend/tests
backend/.venv/bin/python -m pytest devices/printer/tests
python3 scripts/test_compose.py
```

Tests require a disposable PostgreSQL URL, never production. Current counts and incomplete runtime checks belong in the [status report](docs/status-report.md), not an inherited review verdict. Production source/dump/media reconciliation, migration, SMTP delivery, USB output and production performance remain separate work. No push, PR, merge or production rollout is authorized.
