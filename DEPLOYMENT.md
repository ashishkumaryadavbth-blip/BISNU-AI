# BISNU-X production deployment

## Recommended architecture

```text
Flutter Android app
       |
       | HTTPS / SSE (BISNU_API_URL)
       v
Railway Hobby or Pro - Dockerized FastAPI API (Dockerfile at repository root)
       |                         \
       | TLS                     \ HTTPS (OpenAI-compatible API)
       v                           v
Neon PostgreSQL (Launch)       LLM gateway provider
       |
       +-- accounts, password hashes, conversations, messages, and memory

Better Stack (optional health checks and alerts) ---> GET /health
Railway API -- future upload adapter --> Cloudflare R2 (private object bucket)
```

The shipped client is Android-only, so Vercel is not part of the request path.
A Vercel static site is optional if a separate marketing site is added later.

Keep the existing BISNU-X username/password authentication. Account IDs are
`username#bisnu-x.com`; the suffix is not a mailbox. The API already hashes
passwords and issues its own bearer tokens, so Clerk or Supabase Auth would add
a second identity system and require an app/API migration without providing an
email recovery address.

The scanner currently performs OCR on-device and the Android client does not
upload the image. There is no active remote file-storage requirement in this
flow, so do not mount a Railway disk or store scanner images on the API
filesystem. The legacy premium scanner upload endpoint writes to local disk;
keep Premium disabled and do not enable that endpoint for production until it
is removed or migrated to private object storage such as Cloudflare R2.
The app currently has no R2 adapter, so do not configure R2 credentials or
claim uploaded files are stored durably. Add owner-scoped object keys,
short-lived signed access, deletion/retention behavior, and tests before
introducing server-side uploads.

## Free-tier and production trade-off

There is no fully free setup here that provides a continuously available API,
durable backed-up database, and a production uptime commitment:

- Railway Free includes only $1/month of usage and caps each service at
  0.5 GB RAM. It is suitable for trying the deployment, not a production API.
- Neon Free is a permanent plan, but the compute must scale to zero after
  inactivity, storage is capped at 1 GB, and it does not provide the paid-plan
  restore/backup features needed for production recovery.
- Cloudflare R2 currently includes 10 GB-month of Standard storage and monthly
  operation allowances. It is not needed by the current on-device scanner.
- Better Stack's free monitors are useful for personal/testing projects; check
  its current terms before using them for a commercial service.

Recommended minimum production-oriented setup:

- **Railway Pro** for a continuously running Docker API, restart policy, and
  production-oriented plan limits. Railway's Pro plan is $20/month and
  includes $20 of resource usage; usage above the included amount costs extra.
- **Neon Launch** for non-expiring managed PostgreSQL. Disable scale-to-zero
  for the production compute and enable scheduled snapshots/restore according
  to the required recovery point. Neon bills by usage rather than a fixed
  monthly minimum.
- **Cloudflare R2** only when the product adds server-side file uploads.
- **Better Stack** or another monitor for alerts on `/health`.

Indicative low-traffic floor (USD, based on listed pricing checked
2026-10-05, before tax, AI gateway charges, egress, and usage overages): about
**$40/month**. This assumes Railway Pro's $20 base plan
and low API usage within its included credit, plus one Neon Launch compute at
0.25 CU kept on for a 730-hour month ($0.106/CU-hour = about $19.35), 1 GB
database storage ($0.35), and approximately $0.29 for 1 GB of Neon restore and
scheduled-snapshot storage. Railway CPU/memory use, traffic, database growth,
and model-provider tokens can increase this. Recheck provider pricing and set
spending alerts before provisioning. Railway's listed contractual uptime SLA
is Enterprise-only; Pro is not an SLA.

For a lower-cost pilot, Railway Hobby ($5/month including $5 usage) with Neon
Launch can reduce the platform base by about $15/month, but it is not the
recommended production plan for a public app. Neon Free is appropriate only
for development/temporary staging where scale-to-zero and weaker recovery are
acceptable.

## Deployment steps

### 1. Prepare the source repository

Push the project to a private GitHub repository. Do not commit `.env`,
`key.properties`, keystores, database files, or model-provider keys.
The root `Dockerfile` runs FastAPI on Railway's injected `PORT`, requires
`DATABASE_URL`, enables gateway mode, and disables local model weights.
Provide the environment variables below for the production database and
external gateway.

### 2. Create the persistent database

1. Create a Neon project in **AWS Asia Pacific (Singapore)** to keep it near
   the Railway Singapore service.
2. Select the **Launch** plan for production. Use a small compute (start at
   0.25 CU), turn off scale-to-zero, and configure scheduled snapshots and
   restore retention.
3. Copy the **pooled** connection string for the application. Keep a separate
   direct connection string for database administration and bulk migration.
4. Never commit either connection string or paste it into chat.

Neon fixes the project region at creation; moving it later requires creating a
new project and migrating the database.

### 3. Deploy the API on Railway

1. Create a Railway project from the GitHub repository and select the
   **Singapore** deployment region.
2. Configure the service to use the repository root Dockerfile (`Dockerfile`)
   with the repository root as the build context.
3. Set the health-check path to `/health`, start command to the Dockerfile
   default, and restart policy to restart on failure.
4. Add the server environment variables in the Railway service's Variables
   page (see the table below). Add secret values there, not in source control,
   a Docker build argument, or the Android project.
5. Deploy and wait for `/health` to return HTTP 200. Save the stable HTTPS
   Railway service URL.
6. Check `/api/status` and verify it reports
   `database_connected=true`, `database_backend=postgresql`, and a configured
   LLM gateway. Both `/health` and `/api/status` issue a live `SELECT 1`;
   database failures return HTTP 503 and a sanitized log entry. Then exercise
   account registration/login, chat, search, and conversation restoration.

### 4. Environment variables

Set these **on the Railway API service**:

| Variable | Required value | Secret? |
| --- | --- | --- |
| `DATABASE_URL` | Neon pooled PostgreSQL connection string | Yes |
| `BISNU_REQUIRE_PERSISTENT_DB` | `true` (refuse accidental ephemeral SQLite) | No |
| `BISNU_JWT_SECRET` | Random secret of at least 32 bytes; use Railway's generated secret facility | Yes |
| `LLM_GATEWAY_ENABLED` | `true` | No |
| `LLM_API_BASE_URL` | HTTPS OpenAI-compatible API base URL from the chosen gateway | Usually no |
| `LLM_API_KEY` | Gateway API key | Yes |
| `LLM_MODEL` | Exact model ID enabled for that API key | No |
| `QWEN_ENABLED` | `false` (no local model weights on Railway) | No |
| `LLAMA_ENABLED` | `false` (no local model weights on Railway) | No |
| `BISNU_ENABLED` | `false` unless real BISNU weights are supplied | No |
| `ENSEMBLE_ENABLED` | `false` for gateway-only inference | No |
| `VERIFIER_ENABLED` | `false` for gateway-only inference | No |
| `SYNTHESIS_ENABLED` | `false` for gateway-only inference | No |
| `MAX_CONTEXT_LENGTH` | `8192` initially; tune to provider/model limits | No |
| `MAX_NEW_TOKENS` | `512` initially; tune to provider/model limits | No |
| `LIVE_SEARCH_ENABLED` | `true` if live search is desired | No |
| `PORT` | Do not set manually; Railway injects it and the Docker command reads it | No |
| `BISNU_ADMIN_KEY` | Optional random secret to enable the protected admin model-status route; leave unset to keep it disabled | Yes |

Payments are intentionally excluded. Leave Razorpay variables unset; Premium
and scanner access remain Coming Soon/locked.

Future R2 adapter variables (not read by the current app; do not set yet):
`R2_ACCOUNT_ID`, `R2_BUCKET`, `R2_ACCESS_KEY_ID`, and
`R2_SECRET_ACCESS_KEY`. The endpoint would be
`https://<R2_ACCOUNT_ID>.r2.cloudflarestorage.com`; use a private bucket and
short-lived signed URLs. Add these only together with tested R2 upload,
ownership, and deletion code.

`BISNU_API_URL` is **not** a backend environment variable. It is a build-time
value supplied to Flutter and must be the Railway HTTPS URL:

```powershell
flutter build apk --release --target-platform android-arm64 `
  --dart-define=BISNU_API_URL=https://YOUR-RAILWAY-SERVICE.up.railway.app
```

Do not build a public release until the backend is live, the gateway is
verified, and the new upload keystore has been registered with Play Console
when applicable. The compromised old keystore and root `key.properties` were
removed. A replacement key is now stored outside OneDrive at
`%LOCALAPPDATA%\BISNU-X\signing\bisnux-upload-key.jks`; its local
`key.properties` is protected by a user-only ACL. Exported public certificate:
`%LOCALAPPDATA%\BISNU-X\signing\bisnux-upload-certificate.pem`. Set the local
`BISNU_SIGNING_PROPERTIES` environment variable to that properties-file path
before invoking `flutter\build-release.ps1`. Keep a separate encrypted offline
backup of the private keystore and passwords before public release.

### 5. Monitoring and operations

- Configure a Better Stack HTTPS monitor for `https://YOUR_API/health`; alert
  on repeated failures and elevated response time.
- Review Railway usage and set a spending limit/alerts.
- Enable Neon scheduled snapshots and periodically test restoring one.
- Keep model-provider API limits and budgets enabled.
- The app's current in-process rate limiter is not a distributed abuse-control
  system. Keep one API replica until a shared rate limiter is implemented.
- Do not advertise scanner uploads, remote image analysis, or payments as
  active until their server-side production paths have been implemented and
  tested.

## Migration from Render

No live Render deployment or Render database is configured in this workspace
at the time this guide was written. If a Render database was created outside
this workspace, perform a planned migration before switching the Android API:
do not use a Render Free Postgres database as the production source of truth;
its current documented expiry/deletion policy makes it unsuitable for durable
account and chat history.

1. Create the Neon production project and a fresh target database. Keep the
   target empty.
2. Temporarily pause writes to the Render API so the final dump is consistent.
3. From a trusted machine with PostgreSQL client tools, use Render's private
   or external source connection and Neon's **direct** target connection. Keep
   both URLs in process environment variables, never in source files:

   ```powershell
   pg_dump --format=custom --no-owner --no-acl `
     --file=bisnu-render.dump $env:RENDER_DATABASE_URL
   pg_restore --clean --if-exists --no-owner --no-acl `
     --dbname="$env:NEON_DATABASE_URL" .\bisnu-render.dump
   ```

   `--clean` removes matching objects in the target; use it only for the
   deliberately empty migration target.
4. Compare row counts for users, conversations, messages, memories, payments,
   and revoked tokens using read-only SQL on both databases. Test a migrated
   user's login and history restoration in a staging API.
5. Set Railway's `DATABASE_URL` to the Neon **pooled** string, deploy, and
   re-run the API/auth/chat/history smoke tests.
6. Point a test APK at the Railway HTTPS URL. Once verified, build and test
   the release APK, then move production users to it.
7. Keep Render read-only until backups and user-data checks are complete.
   Delete the old Render services only after an agreed rollback window.

If no Render database exists, skip this migration. The local SQLite file
`bisnu_x.db` is **not** automatically copied to Neon; a separate tested
SQLite-to-PostgreSQL migration is required if its existing user/history data
must be retained.

## References

- [Railway pricing](https://railway.com/pricing)
- [Railway Docker deployment](https://docs.railway.com/guides/dockerfiles)
- [Neon pricing](https://neon.com/pricing)
- [Neon regions](https://neon.com/docs/introduction/regions)
- [Neon scale to zero](https://neon.com/docs/introduction/scale-to-zero)
- [Cloudflare R2 pricing](https://developers.cloudflare.com/r2/pricing/)
- [Better Stack pricing](https://betterstack.com/pricing)
- [Render free-instance limitations](https://render.com/docs/free)
