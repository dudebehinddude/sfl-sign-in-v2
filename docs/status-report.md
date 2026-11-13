# SFL Sign In 2.0 status report

Updated November 10, 2026 for [station restoration and follow-up UI corrections](layout-restoration.md), after local commit a133323. Implementation and runtime checks pass. Primary Sol round 2 approves the current behavior; Composer round 2 approves its Overview correction. No blocker, should finding or reviewer remains pending. Opus is unavailable. Nothing was pushed or deployed to Zund.

## Current preview

http://localhost:8099 runs Vite hot reload; 8098 remains the separate older built preview. Demo accounts are 800000001 superadmin, 800000002 admin and800000003 operator, with local synthetic password `synthetic-demo-password-only`. All three now have cat photos uploaded through the real profile/S3/media path. These are not production credentials or real people.

| Area | Implemented behavior |
| --- | --- |
| Station | Original scanner-left/centered welcome+clock, today's Time In/Time Out/Name/Description table below, and right keyholder photo/statistics sidebar. Shadcn controls and existing scanner/keyholder/registration flows retained. |
| Resizing | Seven Chromium viewports checked. At 800×480 the whole station/sidebar fit without page or sidebar scroll. Input stays visible at least 44px. Narrow portrait can stack; long activity tables scroll inside their region. |
| Occupancy | Training filters restored as a left sidebar, icon beside each training name, photos and completed icons beside users. Phone filters collapse. Original colors remain; the extra white icon tile background is removed. |
| Training icons/order | Image upload to private S3 replaces the icon dropdown. DB stores the key and display_order. Original sticker order is Policies, Orientation, FDM, Laser, Resin, Waterjet. One canonical order feeds definitions, UI badges and printer payloads. Existing six icons were uploaded through the same API. Training Types and record lists have search. |
| Printer | Same-origin bounded artwork retrieval and original fallback assets. Color/alpha retained until monochrome rendering; dithering preserves the orange FDM symbol. No offline queue/replay. No physical USB output tested. |
| Canvas | One overall sync action and last successful whole-sync checkpoint, hourly interval 3600 seconds. Canvas Users stays searchable/paginated. Per-training diagnostics and quoted cache/preservation copy are removed from the sync UI. |
| Storage | Superadmin image thumbnails, hover and click previews through the app, with protected linked objects. Generic upload form/Uploads shortcut removed. S3/DB ports remain internal. |
| Metrics | Previous full calendar month by default. Start/end dates inclusive, including a one-day range; chart/CSV use the same bounds. Fixed Eastern reporting handles DST. No timezone input/exclusive label/explanation. |
| Admin/SQL | Redundant Staff dashboard header removed; desktop collapse/mobile navigation work. Play+Preview SQL+Ctrl+Enter in one button. Reads run immediately; writes retain real transaction previews/Commit/Roll back. Shortcut reads the current Monaco model even after a fast paste. |

## Verification

- 214 backend tests pass without skips in the final Python3.13 preflight image, 31.35 seconds. This includes25 new preflight cases. The earlier station/UI checkpoint had189 tests. The running preview was not redeployed for this standalone tool.
- 116 frontend tests across 32 files, typecheck, lint and production build pass. Local Monaco's existing large-chunk warning remains.
- 79 printer tests and 5 Compose-helper checks pass. Ruff check/format is clean across 61 Python files. Production images build and nginx configuration validates.
- Actual browser workflows prove station entry/exit and visit times, three cat photos, six bucket icons/editor save/sticker order, storage previews, Canvas whole-sync display, both searches, inclusive metrics/CSV, SQL keyboard execution and desktop/mobile navigation.
- The additive display_order migration preserved training, Canvas roster and user counts. Existing 2503-person Canvas cache remains intact. No private Canvas records or runtime secrets are exported in proof/review artifacts.

SMTP remains disabled; recovery does not send mail. Physical printing, actual SMTP delivery, production source/database reconciliation, backup/restore and production migration remain unverified or deferred. User final schema/architecture acceptance remains separate. See the [schema](schema-proposal.md), [decisions](discussion-list.md), [verification log](verification-log.md) and [review ledger](reviews/ledger.md).


## November 10 read-only comparison and migration preparation

The live checkout, schema and aggregate service/data checks were captured through the laptop, with no Zund writes or restarts. The missing bulk Canvas fix is preserved and already matches v2's fetch approach. There are eight categories, including Zund and Shopbot. The old Policies field differs from the assignment ID used by the live task. Confirmed migration concerns include28 duplicate Canvas-ID groups, two visit-state mismatches and21,212 null forgotten flags; old reporting includes those null flags, so the planned mapping is false.

The new standalone read-only exporter/offline preflight checks a future private export without connecting to the target or importing. Password hashes are excluded. Actual user records/media were not exported, and a full-data migration remains unverified. Provenance, credentials/roles, conflicting identity ownership and cutover need explicit policies. [Live comparison and tool usage](research/zund-live-comparison.md) gives the evidence boundary and next steps. This new tooling has its own verification/review, separate from station/UI approval.


Preflight verification:25 focused cases,214 backend tests under Python3.13 with no skips, Ruff across53 files, captured-schema/synthetic restore and a network-disabled installed CLI proof pass. The tool has no apply command or target connection. Primary Sol and additional Composer approve the preflight in one round each, with no blocker/should or pending reviewer. This approval covers preparation only, not production import.
