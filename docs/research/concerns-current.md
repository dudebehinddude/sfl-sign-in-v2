# Current concerns and corrected issue triage

Updated November 9, 2026 for the user's second revision, using their corrections, previously read SFL Discord discussions and repository-baseline research. No new Discord/account reads were made for this revision. The deployed Zund source/database is still unavailable; a historical report without a later fix is **not** automatically a confirmed current bug. Published repository main is baseline `49cfbb7`; the recovered November 7 Canvas task is newer source evidence for that path, not a complete production snapshot.

## Current user concerns and required improvements

| Concern | Current assessment | Evidence / implication |
| --- | --- | --- |
| Slow tap response and difficult maintenance | Active, confirmed by the user; no production benchmark captured | The user reports taps sometimes take several seconds and the live code is difficult to repair safely. Keep tap transactions local and short, with background Canvas/SMTP/printing; measure against the real deployment later. |
| Deployed code differs substantially from GitHub | Active, confirmed by the user | The [old-schema inventory](legacy-schema.md) is explicitly repository baseline `49cfbb7`. Live-only functionality and a correct importer require the later source/database/media snapshot. |
| Schema naming, timestamps and permissions | Current redesign requirements, not newly discovered production defects | The user requests a normalized schema, named access/level enums, created/updated timestamps, granular backend authorization and superadmin-only SQL. The [proposal](../schema-proposal.md) still requires their approval. |
| Frontend and operator tooling | Current user-owned workstream | Familiar but improved Vite/shadcn UI; public read-only occupants with badges/photos; protected diagnostics, administration, charts and CSV. These are explicit user goals, not evidence that every feature was unanimously agreed historically. |
| Clunky keyholder experience | Acknowledged; redesign deliberately deferred | User says keep the current behavior for now, with numeric priority minimum/default `-1`. Preserve opening, takeover, handoff and closing rules; do not invent a new keyholder policy. |

## Discord concerns worth retaining, with status limits

| Concern | Latest evidence supports | What remains relevant |
| --- | --- | --- |
| Missing training badges after course completion | October's fix repaired thirty-something people, then Jeremy reported a remaining case. [Residual report](https://discord.com/channels/1135930182721601617/1461396632695472231/1565723037980958870) | Matching, freshness and sync failures need visible diagnosis. The evidence does not establish that the whole current sync is broken or identify that remaining case's cause. |
| Incorrect emails or absent Canvas membership | These were identified as remaining explanations after the capitalization repair. [Explanation](https://discord.com/channels/1135930182721601617/1461396632695472231/1565720200484098171) | Show unmatched/conflicting identities and support controlled correction; don't silently merge or swap Canvas/Niner ownership. |
| Convenient semester/date-range reporting | Interface was described as seven days/all-time; semester figures were successfully produced later through SQL. [Interface limitation](https://discord.com/channels/1135930182721601617/1461396632695472231/1561833322206863534), [successful totals](https://discord.com/channels/1135930182721601617/1461396632695472231/1566630090824229026) | The supported concern is self-service reporting, not inability to calculate statistics. New charts/CSV should share explicit date/overlap/quality semantics. Current deployed interface needs confirmation. |
| Unfinished registration followed by another scan | August incident; present-day status unverified. [Report](https://discord.com/channels/1135930182721601617/1461396632695472231/1542912443821326448) | Preserve as a regression case: new scan replaces the prior draft and registration carries its identifier explicitly. The user removed persisted device/registration intent machinery. |
| Testing changes on the live station | September concern, separate QA instance proposed. [Discussion](https://discord.com/channels/1135930182721601617/1461396632695472231/1547812527864283157) | Current QA status unverified. Isolated beta configuration and reproducible tests remain sensible requirements; wired networking alone does not prove testing workflow completion. |

## Resolved, historical or excluded

| Item | Correct treatment |
| --- | --- |
| Pi-to-Zund migration, OneIT Ethernet activation and network arrangement | Resolved according to the user. All infrastructure is wired on its own subnet; Zund is host and jump box. Do not carry obsolete Wi-Fi/hosting complaints forward. |
| Someone appearing under another person's name | User identifies a corrected Canvas/Niner ID swap, with no recurrence, possibly associated with migration/export. The [old report](https://discord.com/channels/1135930182721601617/1360328699026604072/1547379740271185971) is a migration regression case, not a confirmed ongoing registration defect. |
| Email capitalization and slow periodic refresh | October repairs were reported. Preserve those fixes. [Diagnosis](https://discord.com/channels/1135930182721601617/1461396632695472231/1565535736537551050) |
| Expired API key caused the October badge incident | Initial diagnosis was revised; do not report it as established cause. [Correction](https://discord.com/channels/1135930182721601617/1461396632695472231/1565197314438729769) |
| November 2 and November 6 printer incidents | Both reported fixed; there is no demonstrated open outage. The new user-selected workflow drops offline/busy labels and uses explicit reprint after unknown output, without a persistent backlog. [November 2 fix](https://discord.com/channels/1135930182721601617/1461396632695472231/1566888969558294660), [November 6 fix](https://discord.com/channels/1135930182721601617/1461396632695472231/1568403309692330017) |
| Wrong training quiz mappings in September | Historical deployment incident, worth regression coverage. [Report](https://discord.com/channels/1135930182721601617/1461396632695472231/1547792977643184230) does not establish that incorrect mappings remain deployed. |
| Physical acknowledgment button and missed-button statistics | Excluded one-off proposal without established agreement. Do not turn it into a requirement or infer staff inattentiveness as a current system defect. |
| Earlier email-delivery and page-load complaints | Later February improvements were reported. [Email fix](https://discord.com/channels/1135930182721601617/1461396632695472231/1470611093641494580), [performance improvement](https://discord.com/channels/1135930182721601617/1461396632695472231/1470612243619119114). The user's current tap-latency report is separate and remains valid. |

## Evidence gaps and decisions

- Live source/dump/media and current mappings are still needed for full parity, identity reconciliation and an executable production importer.
- Real Canvas credentials, SMTP service and USB label hardware have not been verified by deterministic fixtures. Production tap latency remains unmeasured.
- The actual Cloudflare tunnel routing/access configuration is absent from the old repository; [its presence does not establish public exposure](legacy-infrastructure.md). New candidate is LAN-only by default.
- All three original architecture recommendations are historical input. The user's simpler revision supersedes their device/queue/mapping/log design, and old implementation approval does not cover the changed whole source. Final current review and user schema approval remain pending. Opus hit its usage cap; the user authorized Sol to complete the frontend. Current 118 backend/32 frontend checks, synthetic browser proof and simulated printer acceptance are in the primary [status report](../status-report.md), not evidence of production repair or real Canvas/SMTP/USB compatibility.
- Broader door-access, Prusa Connect, checkout/material tracking and the rejected button proposal are not blockers for this sign-in candidate.
