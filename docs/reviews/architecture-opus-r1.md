# Architecture council review, round 1 (frontend and product lens)

I'm **provisionally choosing these options**: TanStack Router with file-based routes, a custom shadcn admin UI (no Refine or React Admin), a FastAPI monolith with a worker and PostgreSQL LISTEN/NOTIFY, durations computed from timestamps, and fixed role presets. The draft has the right direction. It needs about a dozen corrections, and it has three places where it builds more machinery than this app needs.

This is an architecture choice only. It does not approve any implementation, and the user still has to approve the schema.

**What I checked.** All 12 snapshot files match `manifest.json` by SHA-256. I read `project-context.md`, `architecture-council-draft.md`, and every legacy reference file in full. Everything I say about legacy behavior comes from the repository baseline, not from what runs on Zund today.

**What I did not check.** I did not open the T3 Code reference, the personal projects, or shadcn preset `b2BpPb196`. They're outside the snapshot, and there's no network. So the preset's actual contents (Radix or Base UI, icon library, fonts) are still unknown.

## Chosen options

| Area | Choice | Main reason |
|---|---|---|
| Router | Vite + TanStack Router file routes + TanStack Query | Typed search params for filters and date ranges, per-route code splitting, Next-like folders |
| Admin UI | Custom shadcn on TanStack Table + react-hook-form/zod | Admin work is mostly domain actions, not generic CRUD |
| Realtime | Per-topic revision counter + NOTIFY + full snapshot push over WebSocket | Correct ordering and reconnect with the least code |
| Jobs | One durable `jobs` table plus `print_jobs`, claimed with `FOR UPDATE SKIP LOCKED` | Same worker, no Redis |
| Commands | HTTP only; WebSocket is for subscriptions only | One code path for idempotency, CSRF, and errors |
| Durations | Computed from `started_at`/`ended_at`, no stored column | Reports need clipped overlaps anyway |
| RBAC | Role presets defined in code, granular permission checks, superadmin reserved | Removes 3 tables for now |
| Tap locking | One transaction-scoped advisory lock shared by every kiosk command | Keyholder rules read global state |

**Router.** React Router v7 would also work. TanStack Router fits better because the admin pages keep their state in the URL (table filters, pagination, metrics ranges), and TanStack validates and types those search params. Next.js is out because the brief requires create-vite-app. Proposed layout:

```text
web/src/routes/
  __root.tsx
  index.tsx                 public home, links to /present, /kiosk, /login
  present.tsx               public occupancy, no auth
  login.tsx
  me.tsx                    profile self-service
  station/scan.tsx          redirect to /kiosk (kiosk browsers likely bookmark this)
  kiosk/route.tsx           device-session guard, fullscreen layout
  kiosk/index.tsx
  kiosk/pair.tsx
  admin/route.tsx           staff session guard, sidebar layout
  admin/index.tsx, users/index.tsx, users/$userId.tsx, trainings.tsx, visits.tsx,
  keyholders.tsx, canvas.tsx, printing.tsx, metrics.tsx, audit.tsx, devices.tsx
  admin/_superadmin/route.tsx   role guard (UX only)
  admin/_superadmin/access.tsx, database.tsx, sql.tsx
web/src/features/<domain>/  query options, components, hooks
web/src/lib/api/            openapi-fetch client + generated schema types
web/src/lib/live/           one socket manager, useLiveQuery
web/src/components/ui/      shadcn output, left untouched
```

Route files should only define the route and render a page component from `features/`. For types, use `openapi-typescript` with `openapi-fetch` and hand-written query option factories. Skip codegen that writes hooks (Orval, hey-api), because that's a second abstraction layer. Register the WebSocket message models in FastAPI's OpenAPI components so a single generator covers both REST and WebSocket. CI should fail when the generated types are out of date.

**Admin UI.** Rejecting Refine and React Admin comes down to three things:

- **Duplicate data contracts.** Refine's data, live, access, and auth providers would wrap the same REST and WebSocket contract a second time. Its live provider model (publish an event, then invalidate) would sit alongside our revision and snapshot contract.
- **React Admin specifics.** Its realtime package is, to my knowledge, part of the paid Enterprise Edition. I haven't verified that here. Shadcn Admin Kit also ships its own component registry, which would compete with the exact preset.
- **SQLAdmin.** It would be a second UI with a second auth system, and it doesn't give the user the SQL workbench they asked for.

The cost of going custom is CRUD work. Keep that bounded with one server-driven `DataTable` (pagination, sort, and filter all in route search params) and one form pattern. Do not build a generic row editor. Edits go through domain screens or SQL write mode.

Other libraries:

- **Charts.** shadcn charts (Recharts).
- **SQL editor.** CodeMirror 6 with `lang-sql`, lazy-loaded only on `/admin/sql`.
- **Dates.** `Intl` with `LAB_TIMEZONE`, no date library.
- **State.** No Redux, Zustand, or XState. Connection state lives in the socket manager and is read through `useSyncExternalStore`. The kiosk state machine is a reducer over a discriminated union.

## MUST corrections

### Realtime and jobs

1. **Ordered event IDs from the outbox are not a safe cursor.** Bigserial values are assigned at insert time, but transactions commit in a different order. A client resuming from "id > last seen" can skip an event whose lower id committed later. The draft's replay design depends on that cursor.

   Replace it with a `live_topic_revisions(topic, revision)` row. Each domain transaction increments the row for every topic it changes and calls `pg_notify('live', topic || ':' || revision)`. Postgres delivers NOTIFY only after commit, in commit order, and the row lock serializes writers.

   Every API process keeps one LISTEN connection. When a notification arrives, the process recomputes the snapshot once per topic, audience, and revision, then pushes `{topic, revision, data}` to each subscriber. Clients discard any revision at or below the one they already have.

   Then the `change_events` table with audience and payload replay can go. Snapshots here are tiny (fewer than a few hundred people), so resending the whole snapshot is cheaper than maintaining deltas.

2. **Resnapshot after the LISTEN connection drops.** If a process loses its LISTEN connection, it must resnapshot every subscribed topic when it reconnects, because notifications sent in the meantime are gone. On subscribe, read the revision and the snapshot in one REPEATABLE READ transaction so the two always match.

3. **Only some screens are live.** Live topics are `public.occupancy`, `kiosk.station`, `staff.present`, `printing.status`, `device.print_queue`, and `canvas.sync_status`. User, training, and audit tables are plain REST and invalidate their queries after a mutation. That limits realtime to the screens that actually need it.

4. **Client contract.** `useLiveQuery(topic)` stores data in TanStack Query with `staleTime: Infinity` and no refetch interval. While disconnected, the UI shows a visible "reconnecting" state and "last updated" time, and never presents cached data as live. On reconnect, a fresh snapshot always replaces the cache. The server rechecks the session and permissions on every push and every heartbeat, and a revoke event forces an immediate recheck. Public snapshots go through a dedicated `PublicOccupant` response model, and tests assert that forbidden keys never appear.

5. **No offline tap queue at the kiosk.** Queued taps replayed later would break the keyholder rules. If HTTP fails, show "Not signed in. Server unreachable." The tap result comes from the POST response so feedback is immediate, and the snapshot updates the lists afterwards.

6. **Print jobs must expire.** If a printer comes back after an hour offline, it must not print 40 stale name tags. Add `expires_at` and an `expired` state. When a claim's lease runs out, mark the job `uncertain` rather than reprinting it silently, and give operators a reprint button.

### Schema

7. **Ordered enums.** If level enums are stored as varchar, SQL compares them alphabetically: apprentice < certifier < operator < trainer. That breaks the "highest level per training" query and `>= VOLUNTEER` checks. Use native Postgres enums declared in rank order, mirror the order in a Python map, and add a test that pins the order.

8. **Missing tables.** Add three:
   - `devices` (kind kiosk or printer, name, credential hash, last_seen_at, revoked_at). `print_jobs.printer_id` and kiosk pairing both reference it, but the draft never defines it.
   - `jobs` for Canvas refresh and invite email.
   - `academic_terms`, so semester selection in metrics has something to select.

9. **`canvas_assignment_mappings` needs `awards_level`.** Without it, sync can't know which certification level a passing result grants. Write Canvas results into `certifications` in two places. The worker does it during sync. The registration transaction does it when it binds a roster entry by unique normalized email, which is a local operation. Badge reads then come from one table. Sync never overwrites or revokes a manual certification.

10. **Remove the duplicate Canvas identity.** The draft stores the Canvas ID in both `user_identifiers` and `canvas_roster.user_id`. Keep only the unique `canvas_roster.user_id` binding, with a `match_status` (unmatched, matched, conflict) shown in the admin UI.

    I'd also replace `user_identifiers` with a unique `users.student_id` text column. A tap then becomes a single indexed lookup. Keep the identifier table only if the user wants several cards per person.

11. **Visit closure reasons that match legacy behavior.** Legacy has three ways a visit ends:
    - A normal tap.
    - A keyholder handoff, which signs out the old keyholder normally.
    - Forgot, which happens through either "close space" or staff "set forgot".

    The legacy data can't tell those two forgot paths apart. Use `tap`, `keyholder_handoff`, `space_closed`, `staff_marked_forgot`, `staff_edit`, and `legacy_forgot`, with one shared set that decides which reasons are excluded from hours. The draft's `manual` value is ambiguous.

12. **Keyholder shifts.**
    - Add `started_reason` (open, takeover, handoff) and `ended_reason` (takeover, handoff, space_closed, last_out, admin) so the keyholder history page has something to show.
    - Legacy allowed several open shifts and treated the latest as current. The migration must close the extra open rows, and the singleton index (only one open shift at a time) has to wait until that's done.
    - Volunteers (level 30 to 69) can hold shifts, and the kiosk displays them as "Current Volunteer" with a "Closed" title.

13. **Public photos.** Because photos are public, re-encode every upload on the server, strip EXIF (including GPS), and resize it. Include a version in avatar URLs so caches refresh.

14. **No runtime CDN.** Legacy loads Font Awesome, jQuery, and DataTables from CDNs. Bundle everything. If the preset uses web fonts, self-host them with `@fontsource`, because a LAN-only kiosk must work without internet.

### Keyholder logic (keep current rules exactly)

15. **Encode the legacy rules as one tested pure function** that the transaction then applies. Rules from `visit_tracking/views.py`:

    | Situation | Legacy result |
    |---|---|
    | No keyholder, level ≥ volunteer | Rescan to confirm, then the person opens the space and is signed in if they weren't already |
    | No keyholder, level below volunteer | Error "Need a keyholder" |
    | Current keyholder taps, and theirs is the only open visit | Shift ends and the keyholder signs out normally |
    | Current keyholder taps, others present | Dialog listing present volunteers (bold if keyholder level). Another person's scan hands over and signs out the old keyholder (not forgot). "Close Space" marks everyone else forgot. Cancel does nothing |
    | Not in space, level ≥ keyholder (70), priority strictly greater than the holder's | Takeover prompt. Confirming leaves the old holder signed in. "Don't take over" signs in normally |
    | Otherwise | Toggle the visit. Sign-in queues a print job |

    The "only open visit" check is literally `count == 1` in legacy. That probably assumes the keyholder is present, so verify it against live code.

16. **Correctness fixes that don't change the rules.** The user should see these listed explicitly:
    - **Confirmation scans.** A confirmation scan must come from the same person, enforced with a server-issued pending-action token. Legacy accepts anyone's card.
    - **Handoff validation.** Check that the incoming holder is at least volunteer level before changing anything. Legacy signs that person in first and then errors.
    - **Abandoned registration.** Registration creates no user row until it completes. Legacy creates a placeholder user on the first scan.
    - **Scanning during registration.** A scan during registration cancels the draft and processes the new tap. The registration screen also has an idle timeout.

    Do not copy the legacy 2 ms refocus loop. Capture scanner bursts with a capture-phase keydown listener so dialogs and screen readers keep working.

### Tap path and other gaps

17. **External calls legacy makes during a tap.**
    - Sign-in queues `canvas_update.delay` and prints synchronously inside the transaction.
    - Registration sends the Canvas invite email synchronously.

    In the new design, sign-in enqueues a coalesced Canvas refresh for that user as a post-commit job and inserts the print job as a local row. Whether the invite email stays is the user's call (see below).

18. **Feature parity items the draft omits.**
    - The kiosk "Info at a glance" panel: holder name and photo, number in the building, unique visitors today, hours this week, and the "leaderboard of shame" (top 5 forget ratios among users with at least 5 visits).
    - "Recent Activity (Today)": 10 rows, first name, IN or OUT.
    - The clock and the Welcome/Closed title.
    - The staff present page: Set Forgot, Update Canvas Status, and a filter by training.
    - The profile page: visit list, hours last week, hours all time.
    - Who can add a training. The legacy index gates "Add a Training" on any trainer-level certification. Authority to award is a domain rule derived from certifications, not a role, and the training-create view isn't in the snapshot.

    Two items should not be ported. The multi-barcode branch is broken in the repository baseline (`int(generator)`). "Open Printers XX" is a placeholder. Flag both for the live snapshot.

    `set_forgot` has no permission check in the repository baseline. The new design requires a permission for it.

### SQL workbench

19. **A read-only transaction alone is not a boundary.**
    - With the simple query protocol, submitted text like `COMMIT; UPDATE ...` ends the read-only transaction.
    - `SET TRANSACTION READ WRITE` is accepted before the first query takes a snapshot.

    Read mode therefore needs a dedicated Postgres role granted only SELECT, plus a read-only transaction, plus `SET LOCAL statement_timeout` and `lock_timeout`, plus single-statement execution through prepared statements (the extended protocol), on a raw connection pool separate from the ORM session.

    Cap results by fetching cap + 1 rows from a cursor rather than adding a LIMIT. The cancel button calls `pg_cancel_backend`. Audit the statement text, mode, row count, duration, and SQLSTATE, but never the result contents.

20. **Execution model and UX for v1.**
    - **No transactions spanning requests.** Write mode offers "Dry run (rolls back)" and "Run and commit" with a typed confirmation. The UI says that commit runs the statement again and results may differ.
    - **Outcome per execution.** Show Committed, Rolled back (read mode), Rolled back (dry run), or Rolled back (error). Never show a "transaction open" indicator, because no transaction stays open.
    - **Accessibility.** Show the mode as text plus an icon, not color alone, with a persistent write-mode banner naming the instance and database. Announce results in an `aria-live` region ("42 rows, 120 ms, truncated at 1,000"). The result grid is a real `<table>` and shows NULL distinctly from an empty string. The editor follows CodeMirror's Escape-then-Tab convention so keyboard users can leave it, with on-screen instructions. Ctrl/Cmd+Enter runs the query, and a visible button does the same.
    - **CSV export.** Read mode only, labeled "Export re-runs this query".
    - **Database browser.** Read-only in v1.

### Metrics

21. **Define metrics once and use the same server function for chart JSON and CSV.**
    - **Person-hours.** The overlap of closed, non-excluded visits with the window, clipped to the window boundaries.
    - **Open and excluded visits.** Shown as a separate "N still open, not counted" value and a count of excluded visits.
    - **Average length.** Full, unclipped durations of closed, non-excluded visits that started in the window.
    - **Unique and new visitors.** Unique counts distinct users with any visit starting in the window, including forgot visits (as legacy does). New means the person's first-ever visit is in the window. Base this on visits, not `created_at`, because imported rows break `created_at`.
    - **Days.** Bucket by local date in `LAB_TIMEZONE`.

    The legacy weekly hours counted unclipped visits by entry time. The new numbers will differ slightly, so document that.

## Disagreements with the draft

- **Outbox replay.** Replace it with topic revisions, NOTIFY, and snapshot push for the UI, and a jobs table for durable work (corrections 1 and 8).
- **WebSocket command envelope.** Drop it. HTTP keepalive on the LAN is fast, and two command transports double the places that need idempotency, CSRF, and error mapping. The brief says WebSocket mutations only "where useful", and I don't see where they would be.
- **Per-user serialization.** Use one global advisory lock for all kiosk commands instead. The rules read global state (open visit count, current shift), and a tap transaction takes milliseconds.
- **Roles tables.** Drop `roles`, `permissions`, and `role_permissions` for code presets: `lab_staff`, `admin`, `superadmin`. Store assignments in `account_roles`. The code still checks granular `Permission` enums, so moving to editable roles later is cheap.
- **Durations.** Compute them. A stored generated column is wrong for every clipped report and invites someone to sum it by mistake. If the user wants a named column, use a Postgres 18 virtual generated column, which takes no storage and can't go stale.
- **Compose project name.** Use `name: sfl-signin-${APP_INSTANCE:?}-${APP_PORT:?}`. Copying the prod env file and changing only the port then starts a separate empty project instead of reusing prod's volume. Show the instance name in the app header for non-prod and on the SQL page.

## Optional improvements

- Serve the built SPA from FastAPI in the production image, with no nginx container. In dev, Vite proxies `/api` and `/ws`.
- Replace the `files` table with avatar columns on `users`.
- Ignore the same ID scanned twice within about 5 seconds on one kiosk and return the previous result. Legacy toggles the person straight back out. This changes behavior, so it needs the user's approval.
- Show a 3-second result banner ("Signed in: Jane") in an assertive `aria-live` region, on top of the familiar recent-activity table.
- Map the legacy level colors (red, green, blue, gold) and icons to preset CSS variables. Add text labels so badges don't rely on color, with accessible names like "Laser Cutter, Operator". Check the contrast.
- Store `holder_access_level` on each shift so history stays accurate after someone's level changes.
- Shadcn preset setup:
  - Scaffold with `pnpm create vite`, then apply the preset through the official CLI.
  - Commit `components.json`.
  - Log the CLI version and its output.
  - Check whether the preset picks Radix or Base UI and which icon library it uses before writing components.
  - Put the TanStack Router plugin before the React plugin in the Vite config.

## Decisions the user still has to make

1. Public occupancy names. Legacy shows full names only behind volunteer login, and the kiosk shows first names. Choose full names or first name plus last initial.
2. "All badges" means one badge per training type at its highest level (legacy behavior). Confirm, or show every level.
3. Keep the leaderboard of shame on the kiosk?
4. Registration email domains. Legacy accepts only `@charlotte.edu` at registration, while matching also accepts `uncc.edu`.
5. Keep the Canvas invite email as an async job, which needs SMTP config, or drop it?
6. In legacy, a brand-new user can register and get signed in with no keyholder present. Is that a bug to fix or a rule to keep?
7. Should SQL write mode allow schema changes (DDL), or only data changes? I recommend data changes only (enforced by role grants) and Alembic for schema changes.
8. Default auth roles when migrating from legacy access levels. Legacy staff pages required keyholder level or above; the present list and Set Forgot required volunteer or above.
9. How ordinary users log in to `/me`. One option is password accounts for everyone; the other is staff accounts only in v1.
10. Printer policy: how long before a job expires, and whether to auto-retry within that time.
11. Whether to ask visit purpose at all. I recommend not prompting on every tap.
12. Default the kiosk to dark mode (legacy is dark), and pin Postgres 18.
13. Trainer and certifier award rules. These need the live source.

The live code and database snapshot still need to confirm the keyholder table, the `count == 1` rule, `set_forgot` behavior, the batch scan branch, and whether the Canvas `sis_user_id` equals the 800 number. That last one decides whether registration can pre-fill names from the roster.