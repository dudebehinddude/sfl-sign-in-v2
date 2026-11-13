# Prior decisions, user conventions and note search

This file separates the current user's instructions from historical discussions and observed project conventions. The latest user instructions control the new candidate. Another contributor's unpublished implementation is unavailable; no judgment about its actual schema, frontend or progress follows from the public placeholder repository.

## Explicit current decisions

| Topic | Current direction | Review boundary |
| --- | --- | --- |
| Product | Complete candidate rewrite, frontend and backend; copy familiar workflows while improving them | User will inspect overall design and schema |
| Frontend | pnpm, Vite React/TypeScript, exact shadcn preset `b2BpPb196`; Opus 5.5 lead | User has frontend control |
| Routing | User suggested Next-like routing and T3 Code structure | Vite-compatible file-based routing needs explanation, not silently replacing Vite with Next.js |
| Backend/storage | FastAPI, PostgreSQL, SQLModel direction | Council recommendation provisional; schema still for user approval |
| Data | Clear tables/columns, meaningful relationships, created/updated timestamps, auditability | Old/new mapping and unresolved alternatives must be visible |
| Live data | WebSocket updates with no polling, plus traditional APIs | Reconnection and cross-process consistency required |
| Access | Named enums and granular permissions, independent of physical access | Full-control/SQL is superadmin-only |
| Keyholder | Existing rules for now, minimum/default numeric priority `-1` | Larger UX/rules redesign later |
| Occupants | Public homepage-linked read-only names/photos/badges | Keep identifiers/emails/admin state private |
| Metrics | Admin charts, date-range/semester filters and CSV | Clarify forgotten/open/overlap rules |
| Operations | Better protected operator tools and useful superadmin DB experience | No exposed PostgreSQL port; SQL capabilities enforced server-side |
| Configuration | Environment-driven isolated Compose beta instance and CI preparation | No deployment, push, PR or production migration now |

## Historical architecture discussion recovered in this conversation

- June discussions considered Django, FastAPI, TypeScript, MongoDB and PostgreSQL. Preference/familiarity was a major factor; this was not a settled proof MongoDB was required.
- On August 28, the user and Bayli discussed a typed backend using SQLModel, with PostgreSQL rather than MongoDB. Bayli supported clarity/longevity, and Anthony said the storage technology was flexible if SQL access worked well. [User's SQLModel proposal](https://discord.com/channels/1135930182721601617/1461396632695472231/1542946440412667944), [related typing concern](https://discord.com/channels/1135930182721601617/1461396632695472231/1542948766624260149).
- September discussion proposed using one Pi for QA and one for production because testing on the live station was a problem. Current QA status has not been verified. [Discussion](https://discord.com/channels/1135930182721601617/1461396632695472231/1547812527864283157).
- Existing-system documentation was reported completed with comments and a bulk class registration script in August. A design draft was shared separately. The full Google Docs contents were not read in this task. [Existing-system doc](https://docs.google.com/document/d/1pAOjkghAvpc5jwq2tQlx9koO_hZc4N8ko7JxGC4xGO8/edit), [design draft](https://docs.google.com/document/d/13G-mdMXKu2X7USU9kBPj91WXMLKPbGaY9_B8zBq9V_w/edit).
- Door-access/Grouper/LDAP and Prusa Connect were discussed but are not required to block the current sign-in candidate. Future integration points are sufficient unless the user explicitly expands scope.
- The proposed physical acknowledgment button and missed-button statistics lack established agreement and are excluded.

## User's additional ideas to preserve

- Durable label service plus small kiosk USB printer subscriber.
- Generated interval from sign-out minus sign-in instead of an app-maintained duration counter. Computed final durations are acceptable; distinguish open visits, stored generated values and live elapsed time.
- Sync Canvas people/trainings before first local tap so lookups use local data. A freshness timestamp and visible sync failures are needed; cached does not mean always current.
- Current-occupant API including all badges and photos/fallback.
- More maintainable/contained/portable system, readable typed models, clear naming, timestamps and administrative visibility.

## Conventions observed in existing personal projects

Read-only inspection covered `/home/jussy/git/awesome-project-management-application/AGENTS.md`, its `src/server/db/schema.ts`, and the equivalent AGENTS/schema files in `/home/jussy/git/personal-finance`. No credentials, account rows or unrelated private files were read.

Reusable UI guidance from both projects:

- Use shadcn components first; install through pnpm CLI. Keep `src/components/ui` for generated primitives and prefer component variants/props over editing those files.
- Shared custom components belong in a dedicated shared component location; route-specific components stay with the route.
- Use a shared Typography component instead of scattering typography classes.
- Tailwind is mainly layout and one-off styling; repeated groups should become a component/variant.
- Prefer ordinary functions, typed boundary validation, scoped modules and minimal complexity. Keep README/TODO accurate.
- The finance project's actual short UI titles/actions use Title Case, with explanatory prose in sentence case. This is a project-specific observed preference, not a global instruction that overrides the new frontend's explicit user direction or preset.

Schema observations:

- Project management uses named PostgreSQL role/theme enums, explicit foreign keys, join tables, UUID domain IDs, indexes and timestamps. It documents that ORM relations don't create database FKs and application-side update hooks don't fire for raw SQL.
- Auth tables retain adapter-prescribed names; app-domain fields sometimes use camelCase SQL while auth columns use snake_case. This demonstrates purposeful adapter compatibility, not a universal requirement for camelCase names in Python/PostgreSQL.
- The finance schema uses clear plural table names, source-sync timestamps/cursors/errors, independent overrides and change records, unique/partial indexes, and a mixture of relational and typed JSON data where appropriate.
- Existing projects do not consistently have timestamps on every table. The user's latest instruction to add created/updated fields in this new project takes precedence over copying those omissions.

Implication for new schema: choose a consistent Python/PostgreSQL naming scheme, keep API models explicit, enforce integrity in PostgreSQL, add source/business-event timestamps where they have distinct meaning, and make raw-SQL edits visible. Do not blindly port a TypeScript ORM's JavaScript-only `updatedAt` hook into a system whose superadmin can execute SQL.

## Local notes search coverage and limits

A bounded search checked present top-level notes/vault-like directories, Obsidian vault metadata if present, relevant filenames under `Documents` and `Downloads`, keywords in top-level Documents Markdown, and textual elements of Documents Excalidraw files. No additional SFL/SQLModel/sign-in architecture note was found in that scope. A generic Excalidraw filename existed but did not contain matching SFL terms in readable text.

This does not prove no notes exist elsewhere or in compressed/other formats. The laptop was not contacted or awakened. Existing source comments, project schemas and the known Discord decisions were enough to continue; missing notes are not a blocker.

## User-review questions to keep explicit

1. Proposed new schema, naming and physical-access/application-role separation.
2. Authentication/bootstrap/reset approach, initial role assignments and who may certify each category/level.
3. Whether forgotten-signout leaderboard remains public, becomes staff-only or is omitted from visible UI while preserving underlying counts.
4. Non-university users and Unicode name/email policy, independent from university Canvas matching.
5. Actual lab timezone/semester presets and whether ongoing/forgotten visits contribute to each metric.
6. Superadmin SQL read-only default, explicit write transaction workflow and audit detail.
7. Public photo/badge display and any intended public-name convention on the LAN.
8. Migration details once deployed source/dump/media arrive, including identity conflict reconciliation, password hashes, unknown enum values, and historical fields that never existed.
