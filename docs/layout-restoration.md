# Station layout correction

New user-directed task after local commit a133323. Previous UI approval does not override the user's visual requirements.

- Restore the original station structure from the legacy station.html: scanner upper left, centered welcome/clock beside it, Recent Activity (Today) table below, keyholder photo and Info at a glance in the right sidebar. Keep shadcn controls and existing command/dialog handling. No new top navigation or dashboard redesign.
- Layout changes mean resizing, not an end-user layout editor. Target the Pi screen at800×480 and check1024×600,480×320,desktop and phones. Keep scanner visible, no page-level horizontal overflow and no desktop/Pi page scroll. Narrow portrait may stack naturally.
- Restore occupancy training filters as a left sidebar, with the actual colored training icon beside each name and the people list to its right. Phones may collapse the sidebar. Do not turn the filter into a full-width card grid.
- The original printer-sticker sequence is Policies and Procedures, Orientation, FDM Printing, Laser Cutter, Resin Printing, Waterjet. Store display_order on training_types, default100 for appended custom types. Sort definitions, badge projections and printer payloads consistently; no alphabetical re-sort in the frontend. The admin can edit order. Historical award tables remain chronological.
- Training icons are uploads to the bucket, not a dropdown of hardcoded choices. DB stores an icon key only. Admin/superadmin upload JPEG/PNG/WebP through the app; operator cannot define/upload icons. Public app media serves validated images without exposing S3 credentials/ports. Printer obtains those same immutable icons through the app and keeps its no-replay behavior. Legacy six keys remain a transition fallback, not the editor UI.
- Keep the original color artwork. All six source PNGs already have transparent corners; remove the added white UI background rather than altering or grayscaling them. The physical printer still renders monochrome.
- Three synthetic preview users800000001/2/3 now have CC0 cat portraits uploaded through the real profile API into private S3. No real people changed. Original photos and source URLs live only in task scratch layout-restoration/cats; application/media readback proved JPEG delivery. Do not export real Canvas roster data or private env.

Only the isolated8099 preview may be updated. Preserve8098 and all real Canvas cache data. Apply the additive order-column migration without resetting the database. No production/Zund access, push, PR or deployment. Final verification/review and local commit follow once the coherent correction is ready.

## Follow-up UI corrections included in this task

- Canvas has one overall Sync Canvas action and a genuine last successful whole-sync timestamp. Individual training checkpoints remain internal. Rename the roster to Canvas Users. Remove the quoted preservation/cache explanations; no new logs panel.
- Storage shows safe raster thumbnails, hover previews and click enlargement. Remove the generic upload form and Uploads shortcut; actual avatar/training upload belongs to those edit forms.
- Remove the empty Staff dashboard/separator header. Desktop collapse stays beside the sidebar brand; mobile navigation keeps working.
- The SQL button contains Play, Preview SQL and shadcn Ctrl+Enter keycap. Remove the standalone sentence. Ctrl+Enter must use the editor's current model text, including immediately after paste.
- Metrics default to the previous complete calendar month. Both displayed dates are inclusive, a one-day range is valid, and charts/CSV share the same range. Remove timezone editing, exclusive label and explanation. Reporting uses America/New_York internally with DST; the UI converts its inclusive end to next-day midnight once at the existing half-open API boundary.
- Add search to Training Types and global training records. Record search is server-side over training/user names before count/paging.

## Evidence checkpoint

Primary observed189 tests pass on the frozen Python3.13 image in31.56seconds; backend agent observed the same189 on host in32.88seconds. Frontend116 tests32files/typecheck/lint/build pass; printer79 tests pass; Python Ruff check/format61files and5Compose-helper checks pass. Production images build and nginx config validates. Current runningAPI39source hashes match the frozen backend. Primary Sol round2 approves this behavior; Composer round2 approves the Overview correction. Earlier a133323 approval was not reused.

Actual Chromium checked7viewport sizes including800×480 and480×320. At800×480 the whole station and information sidebar fit with no page or sidebar scrolling; scanner44px is visible, photo loads, activity stays below scanner/welcome. Today rows show actual enter/exit times and an Enter-scanned synthetic visitor registered/signed in/out successfully. Occupancy uses left filters at desktop/Pi widths and collapses on phone, with original color icons and3realuploadedcatphotos.

All6originalicons were uploaded through the realAPI intoS3, including Policies whose .png file actually contains WebP. Input accepts JPEG/PNG/WebP and stores normalized alpha-preserving PNG. Public media, reference saves, editor upload/Save, stored order0–5 and same-origin printer cache/render were observed. Original package assets stay unchanged. A monochrome preview exposed orange FDM losing nearly all ink at fixed threshold; two failing raster regressions now pass with software dithering, preserving monochrome output. No physicalUSB printing occurred.

Actual admin flows pass whole-sync metadata/Canvas Users, desktop/mobile controls, both training searches, storage preview/enlargement, inclusive last-month/one-day dates and matching CSV, and Ctrl+Enter executing an immediately pasted SELECT. Reproduction caught stale React editor state; shortcut now reads Monaco's model. Browser scripts were corrected for duplicate Close controls and the single combined keycap. Shared preview resizing twice reported1280×800 for800×480; after explaining that the primary used headless Chromium. The owned shared tab was closed.

Task-only aggregate/synthetic proofs live in scratch layout-restoration/{layout,occupancy,avatar,migration,training-icon,sticker,scanner,admin}-proof.json. No private env or real Canvas roster payloads/screenshots are included. SMTP stays disabled, prior8098 preview and all existing8099 data remain preserved, and production source/migration remain deferred.

## Composer round1 Overview correction

Composer found one remaining per-training aggregate in the admin Overview. CanvasSummary now uses only the whole-sync overview status, last_success_at and last_error, matching the Canvas screen. Three focused regressions failed before and pass after the correction; all116frontend tests/typecheck/lint/production build pass. Actual Overview browser proof confirms the real whole-sync checkpoint with no per-training counts. No backend or scheduling changes. Proof: scratch layout-restoration/overview-proof.json. Composer round2 approves the Overview correction. Primary Sol identified a separate stale public catalog, corrected below; primary Sol round2 approves the final behavior.


## Public sidebar live correction

Sol found that already-open occupancy screens retained old catalog order/icons. Four regressions failed before the fix and pass after. The public socket now invalidates the catalog for new revisions and authoritative reconnect snapshots, including restored counters, and on explicit invalidation. Stale/equal non-authoritative snapshots are ignored. The mounted sidebar followed a real admin icon/order edit and its restoration without a reload. No polling or backend changes were added. Full116 frontend tests32files/typecheck/lint/build pass. Proof: scratch layout-restoration/live-catalog-proof.json. Focused primary Sol round2 approves the final behavior; no received blocker/should remains.
