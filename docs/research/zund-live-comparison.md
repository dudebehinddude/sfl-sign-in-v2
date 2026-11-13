# Zund source comparison and migration preparation

Read-only inspection on November 10, 2026 used the laptop's passwordless SSH connection to `/home/SFL/Old-Management-System/ManagmentSystem`. The deployed checkout is at `1f1ac5373303ec6044445d1cdb3c42775d7aa80d`, with local changes in `users/models.py` and `users/tasks.py`. Web, worker and beat bind that source directory. This supersedes GitHub-only assumptions about the current deployment. It does not authorize changes to Zund or establish that a migration has run.

The private capture lives under the session scratch directory `zund-readonly-2026-11-10`. It contains 85 source/config/template/icon files with obvious embedded secrets redacted, a schema-only dump, exact aggregate checks and service metadata. No user rows, password hashes, sessions or user photos were retained. Source files include existing account references and must be sanitized further before external sharing. The new repository receives only aggregate findings and nonsecret assignment mappings.

## Confirmed parity

| Live behavior | V2 comparison |
| --- | --- |
| All submissions fetched once per assignment, then indexed by Canvas user ID | V2 already uses paginated assignment submission lists, with a roster pre-sync off the tap path. No per-user submission fetch is needed. |
| Policies score at least 7; other trainings require a non-ungraded result with a grade | Matches v2's threshold versus grade rules. The recovered local change also guards a missing policy score. |
| Email trim/case handling in Canvas lookup | V2 canonicalizes email, supports both university domains and exposes ambiguous identity reconciliation. Existing linked IDs are not silently replaced. |
| Canvas beat task enabled at minute 0 each hour in America/New_York | V2's existing default is a 3600-second interval. No additional scheduler was added. Source beat dispatch timestamps do not prove successful task completion. |
| Six sticker icon positions | Existing v2 display_order matches Policies, Orientation, FDM, Laser, Resin, Waterjet. |
| Eight stored training categories, including Zund and Shopbot | V2's catalog is dynamic and can hold all eight. Migration must not treat the six-category demo seed as an authoritative list. |
| Null forgotten flags are included in old profile/chart hours | Map null to false, preserving this behavior. Do not exclude 21,212 older visits merely because the flag was absent. |
| Old space levels and priority ordering | Map 0/30/70/100 to 0/1/2/3. All negative priorities become -1, preserving nonnegative order. |

The old per-user Canvas-ID lookup still scans course profiles when an ID is absent, and the old tap path still does printer work inline. Those are reasons for the existing v2 design, not new functionality to restore.

## Exact captured counts and checks

| Entity | Rows |
| --- | ---: |
| Users | 3,088 |
| Visits | 24,930 |
| Training records | 3,038 |
| Training categories | 8 |
| Keyholder history | 1,506 |

These are counts from one read-only database snapshot, not stale PostgreSQL row estimates. There are 28 duplicate non-null Canvas-ID groups, 1,647 users without a Canvas ID, 33 nonempty emails outside the current university-domain rule and three IDs outside the usual 80xxxxxxx pattern. A nonstandard prefix alone does not mean a nine-digit identifier is invalid; v2 also supports issued lab identifiers. The importer must preserve or explicitly resolve legacy exceptions rather than silently drop accounts.

There are 68 visits without exit times, no users with multiple such visits, two occupancy-flag/timestamp disagreements, no negative visit durations and one open keyholder shift. Every negative priority is -10, covering 3,052 users. The offline preflight checks additional invariants, including overlaps and foreign keys, when actual rows become available; the aggregate capture does not establish that those checks pass.

## Mapping and data decisions

1. **Canvas ownership conflicts.** Do not pick the first or latest local user for a shared Canvas ID. Preserve both source accounts and require explicit ownership resolution. These duplicates do not establish the cause of the previously fixed swapped-ID incident.
2. **Policies quiz versus assignment ID.** The old category stores 556178, but the live bulk task fetches assignment 2839627. The verified source mapping is in [zund-canvas-assignments.json](zund-canvas-assignments.json). Treat mappings as proposals for later Canvas catalog validation, not instructions to copy every category canvas_id directly.
3. **Legacy training provenance.** Existing rows contain a user, category, level, certifier and completed_on, with no source or submission ID. The automated task also uses a normal account as certifier, so that account does not prove manual origin. The current v2 CHECK permits manual or Canvas ownership only. An import needs an approved representation for unknown legacy provenance, retaining all historical awards and certifiers. Do not invent submission IDs, label every row manual or deduplicate history into one badge.
4. **Passwords and roles.** Django hashes do not match v2's current scrypt encoding. The read-only exporter includes only algorithm labels, never hashes. Decide whether to use controlled password resets or a separately reviewed compatibility/rehash path. Old is_staff/is_superuser and physical space_level must not automatically become v2 administrative authority. No account was changed or disabled during this investigation.
5. **Timestamps.** Existing visit/shift/training timestamps can be preserved. Old users and category rows lack creation/update timestamps. V2 defaults can record import time, but cannot be described as historical account creation time. Preserve raw source history in the private migration backup.
6. **Media.** The live media directory has 26 files totaling 38,554,895 bytes. A later private transfer must validate image content, upload through the app/bucket path and map the old user_picture references. Media was not copied in this inspection.
7. **Occupancy cutover.** The two conflicting legacy flags need explicit correction policy, and a later export must establish an agreed cutover instant. Do not manufacture exit times or silently close all visits.

## Read-only tooling

`python -m app.legacy_preflight` is independent of app startup and the normal DATABASE_URL. It has only two commands:

```sh
# Optional future export from an explicitly supplied source DSN environment variable.
# Run only against an authorized source. The output contains personal records.
python -m app.legacy_preflight export \
  --source-dsn-env LEGACY_SOURCE_DATABASE_URL \
  --output /private/legacy-source.json

# Offline checks. This command never connects to PostgreSQL.
python -m app.legacy_preflight inspect \
  --input /private/legacy-source.json \
  --canvas-mappings docs/research/zund-canvas-assignments.json \
  --output /private/legacy-preflight.json
```

Use the backend virtual environment from the repository root, or the installed backend package. Export opens one REPEATABLE READ READ ONLY transaction with database-enforced default read-only mode and bounded statements, selects fixed columns from the five legacy domain tables, then rolls back. It omits password hashes, last_login, sessions, auth groups and permission membership tables, job payloads, tokens and media bytes. Each new output file uses mode 0600 and refuses to overwrite an existing file or symlink. Store source exports outside this repository; source data and private file paths must not be attached to reviews.

Inspection accepts the documented JSON format, rejects unexpected fields such as password, validates timestamps with explicit offsets and reports aggregate codes/counts. It does not modify input, choose Canvas owners, normalize source accounts in place or discard training rows. Source profile person-seconds use actual instants across DST, completed timestamps and the old false occupancy flag; forgotten rows stay excluded. Legacy charts did not apply that occupancy flag, so the two conflicting rows must be resolved before comparing their totals. Extra categories are retained in counts without requiring a Canvas assignment.

Exit 0 means structural checks passed, 2 means a blocking source conflict, and 1 means invalid input or an operational failure. Decisions remain visible even when structural checks pass. `ready_for_import` and `apply_supported` are always false. There is no apply command or target database connection. This is preparation for a proper importer, not an importer or a full migration backup.

## Remaining evidence

Synthetic tests exercise the captured conflicts and a concurrent source update. They verify that PostgreSQL rejects attempted writes during export, the five tables share one snapshot, raw hashes do not leave the source and inspection makes no connection. A separate local proof restores the captured schema and uses only synthetic rows. These checks do not establish the correctness of an actual full-data migration.

A later approved private data/media export, conflict resolutions, target import implementation, record/count/report reconciliation and restore rehearsal remain necessary. No production export of individual records, application change, restart, email, print, push, PR or deployment was performed.

The live service inventory also confirms running cloudflared and an unrelated robotics github-sync container. The tunnel's public hostname/routing was not inspected. Do not infer that the web app is public from the container alone. Robotics source and credentials remain outside scope.


## Local completion checkpoint

All214 backend tests pass without skips in the Python3.13 image, including25 preflight cases; Ruff passes53 backend files. Captured-schema and network-disabled installed CLI proofs pass. Sol primary and Composer additional approve the immutable tooling snapshot in one round each. No received blocker/should or pending reviewer remains. Existing app/UI/schema/auth/worker behavior was unchanged. A local commit records this preparation; no remote or production write is authorized or performed.
