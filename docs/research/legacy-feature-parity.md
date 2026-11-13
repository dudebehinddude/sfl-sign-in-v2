# Legacy functionality and parity checklist

November 10 update: [the read-only live comparison](zund-live-comparison.md) now confirms the deployed bulk Canvas changes, hourly schedule, schema and migration anomalies. The repository-baseline inventory below remains historical; later user instructions removed training tiers and print queues and override its older replacement suggestions. No full-data migration is claimed.

Baseline: `ManagmentSystem` fetched `origin/main` commit `49cfbb78217792395f77f6745d18e02bfd895a3f`. This is a source inventory, not a claim about the divergent Zund deployment. New implementation statuses must be maintained separately; an unchecked item here is not implicitly implemented.

## Routes and visible workflows

| Legacy route | Repository behavior | Replacement expectation |
| --- | --- | --- |
| `/` | Home links to kiosk, current users for volunteer+, and certification form for trainer+ | Familiar home navigation; current-users link public per latest user instruction |
| `/station/scan/` | Barcode/manual nine-digit Niner ID, toggle normal visit, incomplete-profile registration, keyholder prompts, occupancy/recent activity, weekly hours, forgotten-signout leaderboard | Fast local-only state machine; REST and live updates; reset abandoned registration; don't reproduce broken concatenated-scan branch |
| `/station/new-user/<niner_id>/` | First/last name and university-email form, creates profile, signs in, sends Canvas invitation | Preserve registration and background invitation; no slow Canvas or printer I/O in transaction |
| `/station/set_forgot/` | Force marks active visit forgotten, assigns end timestamp | Authorized staff action with reason/audit; preserve metrics exclusion |
| `/station/close/` | Current keyholder identity confirmation, ends tenure, checks out keyholder, marks everyone else forgotten and closes visits, refreshes leaderboard | Preserve close semantics with proper authorization and atomic updates |
| `/staff/user_list` | Volunteer+ authenticated view, current users, training filters, per-user badges, mark-forgot and update-Canvas controls | New public read-only occupant view has all badges and profile-image fallback; protected mutation tools separate |
| `/training/create/` | Trainer+ certification form, signed-in user selector, allowed category/level choices | Permission-aware certification workflow and valid backend category/level checks |
| `/users/<id>/update_canvas_id` | Forces user's Canvas lookup; POST redirect | Staff action queues sync/matching, returns status without blocking UI |
| `/me/profile` | User's last-week/all-time hours and visit history | Protected self profile with correct identity and visit history |
| `/stats` | Busiest day plus chart interface | Admin-only metrics dashboard with date filters and CSV export |
| `/users-per-day-chart/` | JSON daily visitors, average stay, person-hours, visits/user | Admin API with explicit window/timezone/open/forgotten rules |
| `/admin/` | Django CRUD for users, training categories, training awards, visits and keyholder history; framework auth/group permissions and schedules | New staff management UI plus granular permissions; superadmin-only database tools |
| `/accounts/...` | Django auth URL set, including login/logout, password change/reset views | Deliberate login/session/reset/change support or documented pending SMTP dependencies; don't silently drop account access |
| `/users/` | Placeholder hello-world response | No actual user workflow to preserve |
| `/__debug__/` | Development debug toolbar | Do not expose in deployed candidate; replace with protected diagnostics as needed |
| `/media/...` in debug | Local photo/assets serving | Explicit media storage and safe public-photo delivery, no admin filesystem traversal |

## Exact keyholder business rules to retain for now

1. The active keyholder is the newest `KeyholderHistory` row whose end time is null.
2. `VOLUNTEER` or above can open the lab when no keyholder is active. The kiosk first shows an opening confirmation rather than silently appointing every eligible person.
3. An ordinary user cannot complete normal sign-in while the lab has no keyholder.
4. An incomplete user record is sent to registration before the normal no-keyholder check in this repository. The registration handler itself signs in directly. This is a repository bypass, not a business rule to copy; the replacement must enforce the intended opening rule on registration too.
5. An already signed-in current keyholder tapping while they are the only occupant ends their tenure and signs them out.
6. An active keyholder tapping with other occupants present gets the close/handoff modal. They should not silently disappear and leave the lab unstaffed.
7. A newly arriving `KEYHOLDER` or `STAFF` user whose numeric priority is strictly greater than the current keyholder's gets an optional takeover prompt. Equal priority does not automatically replace the keyholder; volunteers do not enter this priority-takeover branch.
8. Declining takeover continues ordinary sign-in. Priority is not an authentication/admin permission.
9. Explicit handoff accepts `VOLUNTEER` or above, checks them in if necessary, ends previous tenure, creates the next tenure, and optionally checks out the previous keyholder. Reject assigning the same current keyholder again.
10. Explicit close requires confirmation using the current keyholder's scanned identity. Close ends the tenure, checks that keyholder out normally and closes other active visits as forgotten. UI/authentication changes may strengthen authorization without changing this business sequence.
11. Current default priority `-10` becomes minimum/default `-1` per user instruction. Preserve the ordering of actual nonnegative priority values. A broader keyholder redesign is deferred to the user.

Known source defects must not be preserved as intended behavior: concatenated scans construct an invalid integer from a generator and reference variables before initialization; some direct mutation views have no explicit auth checks; close operations are not one atomic transaction; no database constraints enforce a single active visit/tenure.

## Kiosk contents to account for

- Large scan/manual-entry form, occupancy count, unique visitors today and weekly hours.
- Active keyholder name and photo with fallback.
- Opening, takeover, keyholder departure/close and reassignment dialogs.
- Recent activity list, with newest event based on visit entry/end time.
- Forgotten-signout leaderboard: top five forget ratios among users with at least five visits. Refreshed at close and read from Django cache. This is existing functionality, unlike the excluded proposed acknowledgment button. Whether to keep public display of this leaderboard is a user-review question; preserve the data ability and avoid accidentally exposing extra identifiers.
- Name-tag generation on sign-in, containing name and icons for Policies and Procedures, Orientation, FDM Printing, Laser Cutter, Resin Printing and Waterjet. Category names are hardcoded in the legacy renderer; avoid renaming categories without mappings.
- Legacy printer is Brother QL-810W, label `62x100`, rotated 90 degrees, network backend at a hardcoded private address. New USB agent must preserve usable labels while moving printer setup to environment configuration. Actual USB/device/label testing is deferred.

## Training and identity details

- Highest level per category is used for badges: Apprentice red, Operator green, Trainer blue, Certifier gold. Preserve labels, not arbitrary color-only indicators.
- The certification form attempts to restrict a trainer to categories they possess and levels below their own, while a certifier can award all levels in that category. The repository POST handler does not re-check these restrictions robustly; enforce them on the new backend.
- The repository form limits first/last names to 20 characters, an ASCII letters/spaces/hyphens/apostrophes regex, and only charlotte.edu/uncc.edu emails. These are legacy validation restrictions, not automatically desirable new policy. User previously wanted alumni/nonstudent support; council/user should decide allowed external identities and Unicode names. Do not infer a university-wide identity lookup exists.
- Canvas matching currently loops course members and profiles, matches university email aliases, stores Canvas ID and sends invitation if no match. The sync task knows six training categories and special Policies and Procedures score threshold. New pre-synced records should retain source assignment/mapping and completion provenance with no calls during taps.
- Transactional welcome/Canvas invite email uses Brevo via django-anymail. Real provider credentials, sender domain, enrollment URL and deliverability are configuration/integration dependencies.
- `massRegister.py` bulk-registers class CSV rows by scraping CSRF forms and posting to kiosk endpoints. It also triggers actual sign-in/email side effects. New bulk registration should be explicit, preview conflicts and avoid pretending class preregistration means physical attendance.

## Metrics and calculation semantics

Existing profile totals exclude forgotten visits and include only completed visits. Existing daily chart groups by entry date, counts all visit rows/users, and excludes forgotten visits from duration aggregates. The chart doesn't clip visits to an arbitrary range and its empty-data `min()` call can fail. These are implementation limitations, not desired semantics.

Discord requirements include unique users, total person-hours, average stay, visits and new visitors, arbitrary dates/semester, visual daily series, and CSV export. The November semester totals were successfully generated manually. New dashboard should make that capability self-service, define date/timezone and overlap rules, and distinguish unknown/open durations from zero. Current-occupancy count is a different measure from unique visitors during a period.

## Existing proof is weak

Legacy test files mainly check sign-in/sign-out toggling and a live Canvas lookup using a hardcoded real account. The workflow starts the entire production-like Compose stack and depends on external secrets. Do not reuse real identifiers or external account calls in candidate tests. New proof should cover authorization, active-visit concurrency/idempotency, keyholder transitions, stale/reconnect snapshots, Canvas failure independence, pending label jobs, and reporting boundaries against disposable synthetic data.

## Sources

Repository paths read at the pinned baseline: `visit_tracking/{views,models,forms,urls,nametag}.py`, `users/{models,views,urls,admin,tasks}.py`, `tools_and_trainings/{models,views,urls,admin}.py`, `superfablab/{views,urls}.py`, associated templates/tests, `massRegister.py`, and `.github/workflows/test.yml`. Deployed-only behavior remains to be inventoried from the later snapshot.
