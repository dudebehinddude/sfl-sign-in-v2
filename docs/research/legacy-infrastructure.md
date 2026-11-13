# Legacy infrastructure: what cloudflared and Adminer are doing

Baseline is the tracked `docker-compose.yaml` at `ManagmentSystem` commit `49cfbb78217792395f77f6745d18e02bfd895a3f`. This is historical repository configuration, not the current Zund deployment. The user confirms the live setup is now fully wired on an isolated subnet, Zund is host/jump box, and the database host port was disabled. No live services were inspected or changed.

## Service inventory

| Service | Tracked behavior | New candidate treatment |
| --- | --- | --- |
| `db` | PostgreSQL 17, persistent `pgdata`, health check, fixed `container_name: db`; tracked host port 5432 | PostgreSQL internal network only; separate environment/project volume; no fixed container name |
| `web` | Django development server `runserver 0.0.0.0:8000`, source bind mount, host port 80 | Built frontend/proxy and production-capable FastAPI server; one env-configured host port |
| `celery` | Background worker, same source mount and DB credentials, RabbitMQ broker | Deliberate background sync/job execution, independent of tap transaction |
| `beat` | Celery Beat database scheduler using Django schedule tables | Environment-controlled schedules/worker design; no accidental second scheduler |
| `node` | Node 18 helper runs npm install and CSS build against mounted source | pnpm lockfile and build stage; no startup dependency installs |
| `rabbitmq` | RabbitMQ 4 management image, fixed container name, tracked host AMQP and management ports | Do not add unless chosen architecture actually needs it; no unnecessary exposed management ports |
| `adminer` | Standalone database-admin web UI, tracked host port 8080 | Omit by default; integrated authenticated superadmin-only tools instead |
| `cloudflared` | Cloudflare connector runs a remotely configured tunnel; tracked port 7844 and fixed container name | Omit by default for requested LAN-only app |

Do not report the old host-port publications as current live exposure. The user's later infrastructure facts supersede the repository file.

## cloudflared in plain language

`cloudflared` makes an outbound connection from the lab host to Cloudflare. Depending on the tunnel's remotely configured routing and access policy, it can allow access to a local application through a hostname or private-network route without publishing that application's port directly to the internet. The connector's presence alone does not establish that the sign-in application is publicly reachable. [Cloudflare's overview](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/).

This repository runs `tunnel --no-autoupdate run` and supplies a tunnel token. It does not contain ingress rules, hostname routing, a Cloudflare Access policy or an explanation of why the tunnel is present. Those settings can live in the Cloudflare dashboard. Consequently, the repository cannot establish what service the tunnel reaches, who can reach it, or whether it is still used in the deployed system.

The tracked token is a literal configured value rather than an environment-variable placeholder. It was deliberately not copied into this report, console output or the new repository. Any later reuse of Cloudflare should source fresh credentials through proper secret configuration and verify the actual account/tunnel settings with an authorized operator. No Cloudflare changes are required for this candidate, which should simply omit the tunnel.

The published `7844:7844` entry is not evidence of which app routes are exposed; the tunnel makes outbound connections. It is not a reason to carry this port or connector into the new LAN-only Compose file.

## Adminer in plain language

Adminer is a separate web application for connecting to databases with database credentials. It provides schema/table browsing, row edits and SQL execution. It is not Django admin and does not inherit the sign-in application's user roles automatically.

The tracked Compose file adds Adminer as a separate service with host port 8080, without a route-specific application-role integration. Merely hiding its link inside the React app would not make it superadmin-only. Removing the PostgreSQL host-port mapping also does not stop a container on the internal Compose network from connecting to PostgreSQL; those are different access paths.

For this candidate, omit the unused Adminer service. The chosen protected backend can provide table/schema browsing and SQL results through FastAPI authorization, with superadmin checks on every operation and appropriate database connection/transaction policies. A future external SQL-client route would be a separate explicit design choice, not a reason to publish PostgreSQL broadly now.

## Beta isolation requirements

- One `.env` should select the app's host port and independent environment/project identity. The wrapper/Compose name must ensure a beta environment doesn't reuse production networks or volumes by accident.
- Avoid fixed `container_name` entries, global volume names and duplicated frontend/backend host-port configuration.
- Keep PostgreSQL internal to the project's Docker network. Same-origin proxy routes the app, REST API and WebSocket connection through the single host port.
- Commit only `.env.example`; real DB passwords, session secrets, device credentials, Canvas/Brevo secrets and any future tunnel tokens stay outside Git.
- Prepare future self-hosted runner deployment instructions/workflow example, but do not activate deployment, run against Zund, open a PR or push this task.

## Later production evidence needed

Actual deployed Compose files and overrides, env variable names with values redacted, service/volume inventory, source diff, applied migrations, database dump, media files and any existing reverse-proxy configuration. Tunnel routing/access information only if somebody intends to keep a tunnel. None of these missing live details prevent building the independent candidate now.
