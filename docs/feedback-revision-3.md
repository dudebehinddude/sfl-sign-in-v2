# User feedback revision 3

New task after the approved local candidate bb81f37. User feedback items 1–17 override prior provisional design. No push, PR, production change or deployment. Local new isolated preview and read-only Canvas course requests are authorized. User explicitly authorized using Canvas skill token for testing, without exposing or committing it. Original local demo is synthetic; preserve it until a new isolated candidate works.

1. Responsive kiosk, particularly Raspberry Pi touchscreens; no accidental page overflow or scrolling traps.
2. Denser, practical admin UI and vertical forms, preserving functionality. It is custom React/shadcn over FastAPI/SQLModel, not Django admin or another generic admin framework.
3. Monaco SQL editor, locally bundled workers/assets.
4. Original printer training icon PNGs with tooltips, no textual level pills or certifier/trainer/operator training taxonomy. Each staff account has one nullable role: superadmin, admin or operator; no viewer. Superadmin full app and SQL read/write; admin domain administration and read-only SQL, no credentials/integration-secret config; operator reads most domain data, may assign trainings and edit basic names/account fields, but not space/keyholder/priority/role/access/security changes. Existing recovery-email ownership protections stay. Do not display raw permission strings or recurring own-role badges.
5. Consistent typography. Outfit/preset retained; page title24, section18, subheading16, body14, captions12. Dense rows and predictable vertical spacing; touch controls at least44px on kiosk.
6. Audit uses Time, human action/actor/target labels and relevant record links; raw internal UUIDs are not primary labels. Extend meaningful user/record links elsewhere.
7. Remove repeated self-role display.
8. Synthetic college IDs use80xxxxxxx, not900xxxxxx. This changes seed data, not a blanket ban on issued lab identifiers.
9. User-entered account/registration email accepts only charlotte.edu or uncc.edu, case-insensitively; canonical storage maps aliases once. Apply server-side including imports and matching client validation.
10. Replace pointless external MinIO console redirect with useful in-app storage management. S3/MinIO ports stay internal to Docker. No storage replacement selected.
11. Remove verbose generic/generated copy; useful short labels, descriptions only where needed to make a decision.
12. Raise pagination defaults/caps and expose sensible larger page sizes.
13. Use Canvas skill token for read-only actual SFL course/catalog/submission testing; no grading/submission/enrollment/email writes. Keep real private data out of review snapshots and logs. Do not assume privileges until checked.
14. Remove training definition slug and description. Training tooltips use full names and completion meaning, without inventing levels.
15. Rename certifications to trainings. Merge latest per-person Canvas result fields into training records, without a separate canvas_results table. Shared training_types definitions and cached canvas_quizzes dropdown remain separate. Cache rows can predate local signup through the canonical external identity; independent manual rows stay separate. Preserve config fingerprint protection and successful checkpoint semantics; failed fetches are not revocations. Do not reintroduce duplicate identity binding authority.
16. SQL grids scroll horizontally, preserve readable values, have column visibility controls and hide id by default in normal multi-column browsing.

17. SQL reads run immediately without a mode dropdown or write warning. Writes run inside a real pending transaction and show a change preview. A separate Commit button applies that exact preview; Roll back discards it. No SQL re-execution at commit; ownership, expiry and cleanup are required.

Original six PNGs recovered from legacy visit_tracking/templates, copied verbatim to frontend/public/training-icons. Keys: orientation, policies,3d-printer,laser-cutter,resin-printer,waterjet. Root owns shared badge rendering/tooltips and printer asset integration.

Ownership: backend agent owns backend/** including updated tests/OpenAPI, except new storage route/service extensions coordinated with root. Admin agent owns admin UI/auth/nav/me/types/levels except features/database and new storage UI. Kiosk agent owns kiosk/occupancy UI/features/tests. Root owns shared badge/icon/typography/email helper, SQL/Monaco/grid, storage UI/API, infra/dev preview, live Canvas, integration and review. No nested agents.
