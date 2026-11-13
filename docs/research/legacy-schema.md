# Legacy schema, repository baseline

This describes `UNCCharlotteSuperFabLab/ManagmentSystem` at fetched `origin/main`, commit `49cfbb78217792395f77f6745d18e02bfd895a3f`, dated September 10, 2026. It is derived from the model files and complete application migration chain. It is **not an introspection of the current Zund database**. The user confirms production is substantially divergent; its dump and deployed source will arrive later.

Default Django table names below follow the repository's app/model names; there are no custom `db_table` declarations in these models. PostgreSQL types are inferred from Django declarations, not observed with `pg_catalog`. `DateTimeField` is timezone-aware in the configured PostgreSQL application, with `USE_TZ=True` and display timezone `America/New_York`.

## Domain table inventory

| Table | Purpose | Primary key | Relationship |
| --- | --- | --- | --- |
| `users_spaceuser` | Visitor identity, login account and physical access | `niner_id`, integer | User referenced by visits, certifications and keyholder tenures |
| `visit_tracking_visit` | One stay in the lab | `id`, bigint generated identity/sequence | `user_id` references the user's Niner ID |
| `tools_and_trainings_trainingcategory` | Shared training definition | `id`, bigint generated identity/sequence | Referenced by certifications |
| `tools_and_trainings_training` | A training level awarded to a user | `id`, bigint generated identity/sequence | User, category and certifier references |
| `users_keyholderhistory` | A keyholder's tenure | `id`, bigint generated identity/sequence | `keyholder_id` references the user's Niner ID |

`users_keyholder` was an older model but migration `users/0007` deletes it. Do not assume that historical table is part of the final repository schema. An actual production dump must establish whether all migrations were applied there.

## `users_spaceuser`

| Column | Declaration / expected PostgreSQL type | Null / default | Constraint / meaning |
| --- | --- | --- | --- |
| `niner_id` | `IntegerField`, integer | Required | Primary key; also login identifier via `USERNAME_FIELD` |
| `canvas_id` | `IntegerField`, integer | Nullable | No unique constraint or explicit index |
| `first_name` | `TextField`, text | Nullable, form blank allowed | No database name validation |
| `last_name` | `TextField`, text | Nullable, form blank allowed | No database name validation |
| `email` | `EmailField`, varchar(254) | Nullable, form blank allowed | Not unique; no canonical-email column/index |
| `user_picture` | `ImageField`, varchar(100) path by default | Nullable | `profile_pictures/` upload path; file-extension validator jpg/jpeg/png; stores a path, not image bytes |
| `space_level` | `IntegerField`, integer | Default `0` | Django choices, not a PostgreSQL enum |
| `keyholder_priority` | `IntegerField`, integer | Default `-10` | No declared minimum or database check |
| `password` | Inherited `CharField`, varchar(128) | Required | Django encoded password, not plaintext |
| `last_login` | Inherited `DateTimeField` | Nullable | Last successful login, not created/updated time |
| `is_staff` | Boolean | Default false | Django admin eligibility; separate from `space_level` |
| `is_active` | Boolean | Default true | Login/account status |
| `is_superuser` | Boolean | Default false | Django permission bypass |

`groups` and `user_permissions` are many-to-many relationships in separate join tables. This custom user extends `AbstractBaseUser` plus `PermissionsMixin`; it does **not** inherit the standard Django `username`, `date_joined`, or standard user primary key. There is no `created_at` or `updated_at`.

Physical space levels are `USER=0`, `VOLUNTEER=30`, `KEYHOLDER=70`, `STAFF=100`. These labels are model enums but storage is ordinary integer. Choices are application validation and do not establish an enum/range database constraint.

Computed user properties query visits on demand for last-week hours, all-time hours, all-time completed-visit count and last visit. Hours exclude visits marked forgotten; no durable total exists. `last_visit` assumes at least one visit in repository code.

## `visit_tracking_visit`

| Column | Type | Null / default | Meaning |
| --- | --- | --- | --- |
| `id` | `BigAutoField`, bigint | Generated, required | Primary key |
| `user_id` | Integer FK | Required | `users_spaceuser.niner_id`; Django deletion policy `CASCADE` |
| `enter_time` | `DateTimeField` | Required; `auto_now_add` | Visit start |
| `exit_time` | `DateTimeField` | Nullable | Visit end |
| `still_in_the_space` | Boolean | Default true | Stored occupancy flag, separate from nullable end time |
| `forgot_to_signout` | Boolean | Nullable | Forgotten/forced close flag; no explicit default |

The FK receives Django's usual index. No custom indexes, unique constraints, one-active-visit-per-user constraint, or `exit_time >= enter_time` check are declared. `still_in_the_space` and `exit_time` can therefore disagree without a database constraint preventing it. No duration column exists; durations are computed from the timestamps. `enter_time` is the event timestamp, not a separate record-created timestamp. No updated time exists.

## `tools_and_trainings_trainingcategory`

| Column | Type | Null / default | Meaning |
| --- | --- | --- | --- |
| `id` | `BigAutoField`, bigint | Generated, required | Primary key |
| `name` | Text | Required | Not unique; printing depends on exact category names |
| `canvas_id` | Integer | Nullable | Generic external ID field; actual sync task also hardcodes assignment mappings separately |
| `user_url` | Text | Nullable | Training link; not a URL-typed database constraint |

No timestamps or explicit additional indexes/uniqueness are declared. Do not treat `canvas_id` as the single authoritative assignment map without inspecting live configuration and the sync task.

## `tools_and_trainings_training`

| Column | Type | Null / default | Meaning |
| --- | --- | --- | --- |
| `id` | `BigAutoField`, bigint | Generated, required | Primary key |
| `user_id` | Integer FK | Required | Certified user; Django deletion policy `CASCADE` |
| `category_id` | Bigint FK | Required | Training category; Django deletion policy `PROTECT` |
| `training_level` | Integer | Default `0` | Django choices, not PostgreSQL enum |
| `certifier_id` | Integer FK | Required | Awarding user; Django deletion policy `DO_NOTHING` |
| `completed_on` | `DateTimeField` | Required; `auto_now_add` | Time the local award record was inserted, which may not equal actual Canvas completion time |

Levels: `APPRENTICE=0`, `OPERATOR=30`, `TRAINER=70`, `CERTIFIER=100`. Each FK is indexed by default. No `(user_id, category_id)` or `(user_id, category_id, training_level)` uniqueness is declared. The manager chooses each user's highest training level per category using PostgreSQL `DISTINCT ON`, rather than updating a single award. There are no source, provenance, expiry, revocation, correction-history or updated-time fields.

Migration `0002` backfills a historical certifier for existing rows but does not retain a permanent model default. Do not reproduce that real person's identifier in demo data or assume that account should certify all migrated records.

Django `on_delete` policies above describe ORM deletion behavior. They must not be read as proof that PostgreSQL uses equivalent SQL `ON DELETE CASCADE` clauses. Inspect actual foreign-key DDL in the future dump before migration.

## `users_keyholderhistory`

| Column | Type | Null / default | Meaning |
| --- | --- | --- | --- |
| `id` | `BigAutoField`, bigint | Generated, required | Primary key |
| `keyholder_id` | Integer FK | Required | User; Django deletion policy `CASCADE`, indexed |
| `start_time` | `DateTimeField` | Required, supplied by code | Tenure start |
| `exit_time` | `DateTimeField` | Nullable | Tenure end; null means active |

Current keyholder is the newest row with null `exit_time`. No database constraint declares only one active tenure. No interval-order constraint or record-created/updated columns are declared.

## Framework tables expected from installed apps

These are framework support tables, not additional SFL domain entities. This inventory follows repository `INSTALLED_APPS` and declared dependencies. The live migration state, full support-table DDL and generated primary-key widths must be verified from the production dump. There is no standard `auth_user` because the user model is replaced.

| Table | Fields / relationships relevant to migration |
| --- | --- |
| `users_spaceuser_groups` | Generated join PK, `spaceuser_id` FK, `group_id` FK; unique user/group pair |
| `users_spaceuser_user_permissions` | Generated join PK, `spaceuser_id` FK, `permission_id` FK; unique user/permission pair |
| `auth_group` | Generated PK, unique `name` |
| `auth_permission` | Generated PK, `name`, `content_type_id` FK, `codename`; unique content-type/codename pair |
| `auth_group_permissions` | Generated join PK, group FK, permission FK; unique group/permission pair |
| `django_content_type` | Generated PK, `app_label`, `model`; unique app/model pair |
| `django_session` | `session_key` varchar(40) PK, encoded `session_data`, indexed `expire_date` |
| `django_admin_log` | Generated PK, action timestamp, user FK, optional content-type FK, object ID/representation, action flag and change message |
| `django_migrations` | Migration recorder: generated PK, app, migration name and applied timestamp |
| `django_celery_beat_intervalschedule` | Interval schedule count and period |
| `django_celery_beat_crontabschedule` | Minute/hour/day/week/month expressions and timezone |
| `django_celery_beat_solarschedule` | Solar event and latitude/longitude |
| `django_celery_beat_clockedschedule` | Scheduled datetime |
| `django_celery_beat_periodictask` | Named task, one selected schedule FK, serialized args/kwargs/headers, routing, enable/expiry/start options, last-run/run-count state, change timestamp and description |
| `django_celery_beat_periodictasks` | Singleton change marker used to refresh the scheduler |

`messages` and `staticfiles` do not imply their own database tables. `anymail` and debug toolbar are installed, but this repository declares no application-owned models for them. RabbitMQ state, Docker volumes, media files, and in-memory Django cache are not PostgreSQL tables. No `django_celery_results` app is installed, so do not invent task-result tables.

## Important migration checks, deferred until the actual snapshot

1. Capture deployed source commit/diff, applied migration names, exact table/index/FK/check definitions, sequences and timezone settings before designing the importer against production.
2. Preserve Niner IDs and Canvas IDs as distinct external identities. User reports a previous swapped-ID/name incident was corrected and has not recurred; add explicit identity reconciliation and migration assertions rather than claiming a current bug.
3. Resolve duplicate Canvas IDs/emails/categories and multiple active visits/tenures explicitly. The repository schema does not prevent them.
4. Map known access/training integer values to named new enums; reject unknown values for review. Remap the known legacy priority sentinel `-10` to requested `-1`; investigate other negative values rather than silently clamping them.
5. Preserve forgotten-signout flags and original event timestamps. Do not fabricate historical created/updated values or Canvas completion dates where unavailable.
6. Migrate media files independently from image path columns. Password-hash compatibility, group/permission mapping, session invalidation and preserving administrative history require explicit decisions.

## Sources

- [User model and keyholder history](https://github.com/UNCCharlotteSuperFabLab/ManagmentSystem/blob/49cfbb78217792395f77f6745d18e02bfd895a3f/superfablab/users/models.py)
- [Training models](https://github.com/UNCCharlotteSuperFabLab/ManagmentSystem/blob/49cfbb78217792395f77f6745d18e02bfd895a3f/superfablab/tools_and_trainings/models.py)
- [Visit model](https://github.com/UNCCharlotteSuperFabLab/ManagmentSystem/blob/49cfbb78217792395f77f6745d18e02bfd895a3f/superfablab/visit_tracking/models.py)
- Application migration directories were read through `git show origin/main:<path>`; no production DB was contacted.
- [Django auth reference](https://docs.djangoproject.com/en/5.1/ref/contrib/auth/) and [Celery Beat model reference](https://django-celery-beat.readthedocs.io/en/latest/reference/django-celery-beat.models.html) explain framework concepts; support-table inventory still requires live confirmation.
