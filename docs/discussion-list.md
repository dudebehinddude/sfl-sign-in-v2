# Decisions and follow-ups

This is the review agenda for [feedback revision 3](feedback-revision-3.md), not a request to pause authorized local work or repeat settled choices. The feedback changes have their own Sol/Composer approvals; the previous `bb81f37` review is historical. Final schema/architecture acceptance remains the user's.

## Review the implemented design

1. Compare the [old repository schema](research/legacy-schema.md) with the [new proposal](schema-proposal.md). The November 10 read-only Zund source/schema/aggregate capture now documents live differences; the full private data/media export is still outstanding. See research/zund-live-comparison.md.
2. Review the compact custom shadcn administration, original icon badges/tooltips, public occupancy, responsive kiosk, record links, audit details and larger paging. This is custom React over FastAPI/SQLModel, not Django admin.
3. Review single-role boundaries: operator basic details/trainings/read access, admin domain management/non-superadmin role grants/read-only SQL, and superadmin security/storage/write previews. Training tiers and viewer/multi-role configuration are removed, not pending alternatives.
4. Review SQL preview limits: immediate reads; supported writes held up to 90 seconds; exact before/after Commit/Roll back; one preview per session/two globally. DDL, write joins, UPSERT and protected account edits are not unrestricted SQL administration. If those are needed later, they require a separately reviewed expansion.
5. Review the in-app S3 object browser and referenced-avatar protection. The external console redirect is removed. IAM/credential/server administration is not part of this object-management screen, and no storage replacement has been selected.

## Policies still needing a real decision

- Confirm enrollment/recovery and ambiguous/shared Canvas email correction practice. User-entered university-domain validation is already required; conflicts must never silently merge ownership. Credentialed recovery-email changes remain owner/superadmin-only.
- Decide retention/deactivation/deletion and backup/restore practice. Database timestamp triggers record real changes; they cannot reconstruct missing history.
- Decide whether future confirmed Canvas removals/regrades should explicitly revoke an already earned training. Current latest evidence is separate from accepted award state; failed/nonpassing/missing refreshes do not silently revoke, manual rows remain independent, and revoked awards are not resurrected.
- Confirm report policy/semester presets. Current charts/CSV count overlapping attendance, use closed non-forgotten clipped durations and first-ever visits, sharing a captured clock/snapshot and America/New_York boundaries. No purpose/end-quality taxonomy is pending.
- Decide the inherited forgotten-signout leaderboard's audience. It remains separate from the excluded one-off physical acknowledgment-button proposal.
- Revisit broader keyholder UX later if desired. This candidate preserves volunteer opening/handoff, strict-higher-priority takeover and atomic closure; priority minimum/default -1 is settled.
- Before production, decide a maintained storage/runtime policy and bucket-scoped application credentials. The current S3 service/adapter has not been replaced by alternatives research.

## Integration evidence still needed

Authorized Canvas reads established course 231237 Teacher access, 26 catalog assignments and real submission ID/attempt fields. The full read-only sync succeeded after the historical enrollment-state fix, with 2503 cached people, 14796 training rows and six training types. Unresolved source owners are counted/skipped rather than assigned invented ownership.

SMTP is explicitly disabled; no real mail was sent. Recovery/invitation delivery needs later configured evidence. Printer unit/raster/wheel and simulated transport checks do not establish Brother USB output. Verify actual printer/stock and deliberate unknown-output reprint behavior later. The station/UI follow-up verified its browser workflows at seven sizes, including480×320 and800×480, and passed its production build and review. Physical USB/SMTP and actual migration remain unverified; do not treat the new migration preflight as proof of them. See the [status checkpoint](status-report.md).

## Production migration after the read-only capture

Deployed source/local changes, schema/constraints, service layout, config names, Canvas mappings/schedules and aggregate data concerns were captured read-only on November 10. The local offline preflight prepares a conflict report from a future private JSON export; it never imports. Full data/media, ownership corrections, provenance/password/role policies, target import, counts/report reconciliation and rollback rehearsal remain outstanding. Map old physical access 0/30/70/100 to 0/1/2/3 and every negative priority to -1. Do not fabricate historical timestamps or unseen live-only parity.

The fixed swapped Canvas/Niner-ID/name incident is a migration regression, not an active bug. Pi-to-Zund hosting, OneIT activation and the wired subnet are resolved. [Current concerns](research/concerns-current.md) retains evidence and exclusions; [legacy infrastructure](research/legacy-infrastructure.md) explains why tracked cloudflared/Adminer does not prove current public exposure.

The new local 8099 instance is separate from the preserved synthetic 8098 baseline. Only the explicitly authorized read-only Zund inspection was performed. No production mutation, push, PR, merge, runner installation or rollout is authorized. Current verification/review state is owned by the primary [verification log](verification-log.md) and [review ledger](reviews/ledger.md), not by old approval summaries.
