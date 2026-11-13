# Architecture choices for feedback revision 3

The user's [latest feedback](feedback-revision-3.md), items 1–17, determines this candidate. Earlier advisory reviews are background, not authority to retain rejected complexity. `bb81f37` is the old approved local baseline; the changed source now has separate Sol/Composer approvals. Overall architecture approval remains the user's.

## What the admin interface uses

It is a **custom React/shadcn admin over FastAPI/SQLModel**, not Django admin or a generic admin framework. Vite, TanStack Router/Query, pnpm and preset `b2BpPb196` remain. Shared Outfit typography uses page 24, section 18, subheading 16, body 14 and caption 12. Compact vertical forms, dense tables, larger pages and human record links match the user's requested direction. Healthy connections do not need repeated Live badges; problems remain visible.

| Alternative | Decision |
| --- | --- |
| React Admin or Refine | Their provider/CRUD conventions do not remove kiosk, Canvas, SQL and storage workflows. Not selected. |
| Django admin or SQLAdmin | Would add another UI/authentication model. Not the selected React solution. |
| Next.js | Not selected; the user requested a Vite frontend with the backend kept in FastAPI. |
| Monaco | Selected, including locally bundled workers/assets rather than a CDN. SQL grids scroll, expose column visibility and hide id by default in ordinary multi-column browsing. |

## Data and application services

FastAPI/SQLModel/PostgreSQL is a modular monolith. One nullable native PostgreSQL/Python role sits on users; numeric space access stays separate. One canonical external identity binds a Canvas person to a local user. Manual awards and current Canvas evidence share `trainings`, without a separate result/role-join table or embedded user training blob. Definitions contain name/icon/active and quiz/threshold, without levels, slug or description. [Schema detail](schema-proposal.md) explains ownership and earned-versus-latest evidence.

| Background option | Decision |
| --- | --- |
| Procrastinate/PostgreSQL | Selected for scheduled Canvas/email/expiry work and retries/locking in the library jobs schema. |
| Celery/Redis or microservices | Extra services/contracts are not justified by the current lab stack. Not selected. |
| Custom scheduler/run-history/lease platform | Removed. Printing never enters the background queue. |

Canvas uses one fully paginated assignment-submissions path. The cached quiz dropdown stores the API's assignment ID. Submission ID/attempt and fingerprints protect regrades/configuration; only complete successful application advances checkpoints. Default interval is hourly. The authorized full read-only sync succeeded with 2503 cached people, 14796 training rows and six training types.

## Kiosk, live state and printer

The ordinary internal kiosk uses REST and WebSocket commands without pairing/device/receipt tables. A new scan abandons the previous draft; registration includes its identifier. Keyholder commands name their expected shift, and the server revalidates transitions under a transaction lock. A lost or malformed command reply means refresh and uncertainty, not automatic replay.

Public WS serves names/photos/completed icon badges only, with no student/Canvas identifiers or emails. Private streams recheck role/session state. Public/staff counters serialize through commit; PostgreSQL NOTIFY wakes subscribers and reconnect takes a consistent snapshot. This does not claim universal Convex RPC or offline mutation support.

One API process owns the live printer hub and short-lived SQL preview coordinator. The single printer accepts new labels after attendance commits/responds; offline/busy drops and unknown acknowledgments are never replayed. Original six PNGs/full training names are rendered on fixed stock; the 47 tests/wheel proof are not physical USB proof. Multiple API-process routing/preview ownership is not an established scale-out design.

## Roles, SQL and object storage

Operator reads most domain/audit data, assigns/revokes training and edits basic names/contact details. Admin additionally manages domain access and non-superadmin roles and has read-only SQL. Superadmin alone changes superadmin access, provisions passwords, manages storage and uses supported SQL writes. Credentialed recovery-email ownership restrictions still apply. Integration secrets stay in environment configuration; no permission-list or secret-editor product screen is introduced.

SQL reads execute immediately without a mode dropdown. Superadmin writes run in a restricted, real transaction and show exact changes before Commit/Roll back. Commit never replays the statement. Ninety-second expiry, one preview per session/two globally, bounded preimages/results and cleanup limit held resources. Previewed writes can hold row locks while being reviewed. DDL, UPSERT, joined DML and other unsupported forms are rejected; superadmin is not a PostgreSQL cluster-superuser connection. Dedicated account controls preserve credential/role/activation invariants.

Avatars and object metadata remain in private S3-compatible storage, referenced by user avatar_key. In-app `/admin/storage` replaces the vendor-console redirect and provides bounded object operations/reference protection. It is not an IAM/access-key/server-configuration console. S3 remains internal, and no storage engine was replaced. Existing pinned MinIO and its maintenance considerations are described in the [storage research](research/object-storage-options.md); that comparison did not authorize a migration.

## Reports, environments and remaining evidence

Computed visit durations avoid a maintained duplicate value. Half-open window clipping, completed non-forgotten finalized time, attendance/new-visitor semantics, one captured clock and a consistent JSON/CSV snapshot remain. All timestamps represent one instant; Eastern display/report boundaries include DST.

One explicit env file and APP_PORT select isolated Compose resources and cookies. The new 8099 preview uses `--dev` and `compose.dev.yaml` for Vite hot reload/same-origin API/WS; the prior 8098 demo is preserved. DB/S3 ports, credentials and production data stay private. CI checks/builds; it does not deploy.

Current test/runtime limits belong in [status](status-report.md), decisions in [discussion](discussion-list.md), and future rollout in [deployment preparation](deployment-preparation.md). SMTP is disabled, USB is untested, and production source/dump/media reconciliation is still deferred.
