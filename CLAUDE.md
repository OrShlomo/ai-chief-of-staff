# CLAUDE.md — AI Chief of Staff

Context for Claude Code. Read this first; it is the handoff from the product/planning sessions.

## What this product is
An AI "chief of staff" for mid-level managers who have no office staff. It manages time against goals:
weekly time budgets per goal, smart scheduling with conflict detection and deferral recommendations,
and a weekly budget-vs-actual review with coaching insights.

- PRD: https://claude.ai/artifact/8dSzzqmQ41gYV7AFZr2iMs
- Jira: https://orshlomo.atlassian.net — project key `COS`, Scrum board id 1
- Owner / first user: Or Shlomo (GitHub `OrShlomo`). Talks to the user in Hebrew; code, commits, Jira in English.

## Working agreements
- **Every change references a Jira key** in the commit subject, e.g. `COS-33: ...`.
- One ticket at a time; a ticket is Done only when all its acceptance criteria in Jira are met.
  Work discovered mid-sprint goes to the backlog as a new ticket, not into the current sprint.
- **Ask before** anything that costs money, changes IAM, deletes data/secrets/resources, or touches
  production config. Read-only commands are fine.
- **Never print, log, commit or paste secrets.** Secrets live only in Secret Manager.
  When the owner must paste a secret, use `read -s VAR`, verify with `echo ${#VAR}` (length only),
  then pipe with `printf '%s' "$VAR" | gcloud secrets ...`, then `unset VAR`.
- Keep `main` deployable: features that need config return 503 until configured.
- Every bug fixed gets a regression test.
- The owner is learning PM + cloud practice: briefly explain *why* for non-obvious steps.

## Architecture (ADR-001, see Jira COS-31)
| Concern | Choice |
| --- | --- |
| Language | Python 3.12, FastAPI, psycopg 3, httpx |
| Compute | Cloud Run service `ai-chief-of-staff`, region `europe-west1`, public ingress, request-based billing, min instances 0 |
| GCP project | `ai-cos-or` (project number `838175899464`) |
| Service URL | https://ai-chief-of-staff-838175899464.europe-west1.run.app |
| Database | Neon Postgres, AWS Frankfurt, free plan, pooled connection |
| Secrets | Secret Manager (see table below) |
| Scheduled jobs | Cloud Scheduler (3 free jobs/month) — not used yet |
| CI/CD | Push to `main` → Cloud Build trigger (Dockerfile) → Cloud Run. Env vars/secrets on the service persist across deploys |
| Runtime SA | default compute SA `838175899464-compute@developer.gserviceaccount.com` (tech debt: COS-34) |

Cost target ≈ $0 apart from LLM usage. A budget alert exists (promotional credits excluded). GCP free trial credits end 14 Feb 2027 — design for always-free.

### Secrets and env vars on the Cloud Run service
| Env var | Source | Notes |
| --- | --- | --- |
| `DATABASE_URL` | secret `neon-database-url` | v1 destroyed (was malformed), v2 live |
| `GOOGLE_CLIENT_ID` | plain env var | not secret |
| `OAUTH_REDIRECT_URI` | plain env var | `<service URL>/oauth/google/callback` |
| `GOOGLE_CLIENT_SECRET` | secret `google-client-secret` | |
| `TOKEN_ENCRYPTION_KEY` | secret `token-encryption-key` | Fernet key, generated |
| `ADMIN_API_KEY` | secret `admin-api-key` | generated; guards owner-only endpoints |
| `TELEGRAM_WEBHOOK_SECRET` | secret `telegram-webhook-secret` | generated; Telegram sends it in `X-Telegram-Bot-Api-Secret-Token` |
| `TELEGRAM_OWNER_ID` | plain env var | owner's Telegram user id; everyone else is ignored |

Secret `telegram-bot-token` exists for the owner (setWebhook) but is **not** mounted on the service and
the runtime SA has no access to it: replies go in the webhook response body (COS-33).

IAM: the runtime SA has `roles/secretmanager.secretAccessor` **per secret** (least privilege), not project-wide.
Free tier: 6 active secret versions — 6 used after COS-33 setup (at the limit). New secrets must be granted the same way.

## Code layout
- `app/main.py` — routes: `/healthz`, `/readyz`, `/oauth/google/start?key=`, `/oauth/google/callback`, `/calendar/week` (header `X-Admin-Key`)
- `app/config.py` — settings from env; `GOOGLE_SCOPES` = `calendar.readonly` (write scope comes with COS-23)
- `app/security.py` — Fernet encrypt/decrypt, HMAC-signed OAuth `state`, constant-time compare
- `app/db.py` — Neon access; table `oauth_tokens(provider PK, refresh_token_enc, scopes, updated_at)`
- `app/main.py` `fetch_week()` — current calendar week Sun–Sat local time (`week_bounds` in `calendar/base.py`), shared by `/calendar/week` and the bot; `POST /telegram/webhook` (secret header + owner allow-list)
- `app/telegram.py` — Hebrew week formatting (HTML parse mode, escaped), webhook reply body
- `app/calendar/base.py` — provider-agnostic `CalendarProvider` (Outlook later)
- `app/calendar/google.py` — Google implementation; reads all *selected* calendars, expands recurring events
- `tests/` — pytest; Google API is mocked with `httpx.MockTransport`
- `docs/setup-google-calendar.md` — one-time owner setup for COS-22
- `docs/setup-telegram-bot.md` — one-time owner setup for COS-33

Run tests: `pip install -r requirements-dev.txt && pytest`

## Lessons learned (do not repeat)
1. Revision failed when the runtime SA lacked Secret Accessor → grant per secret before referencing it.
2. Silent `read -s` led to a connection string pasted several times → always validate length/format before storing (COS-35 adds startup validation).
3. Google calendar IDs can contain `#` (`iw.jewish#holiday@...`) → URL-encode IDs; one failing calendar must not fail the whole week.
4. Google OAuth app is in **Testing** mode → refresh token expires every 7 days; reconnect via `/oauth/google/start?key=...`. Publishing needs an owned domain + privacy policy (COS-36).
5. When a user changes a habit ("I no longer train at these times") apply it to the whole series; one-off changes ("move the date this week") apply to one occurrence.

## Current sprint: Sprint 1 – "Validate & walking skeleton" (15–28 Nov 2026)
Goal: validate the core loop by hand (concierge week) and stand up a walking skeleton: Telegram bot that reads my Google Calendar week.

| Key | Item | Status |
| --- | --- | --- |
| COS-15 | Concierge test (manual week) — learnings logged as comments | In Progress (review at end of week) |
| COS-31 | Hosting, DB, secrets, CI | Done |
| COS-22 | Google Calendar OAuth + read week | Done |
| **COS-33** | **Walking skeleton: Telegram bot replies with this week's events** | **In Progress — code done, owner setup pending** |
| COS-26 | Spike: routing APIs with predicted traffic (Waze has no open routing API AFAWK; check Google Routes etc.) | To do |
| COS-13 | Interviews with 5 managers (stretch: 2 of 5) | To do |

Backlog tech debt: COS-34 dedicated runtime SA, COS-35 validate DATABASE_URL at startup, COS-36 publish OAuth app.

## COS-33 (acceptance criteria from Jira) — implemented; finish via docs/setup-telegram-bot.md
- Sending `/week` (or any message) to the bot returns this week's events, grouped by day
- Runs on the deployed Cloud Run service, not a laptop
- Only the owner's Telegram account can use the bot

Suggested design:
- `POST /telegram/webhook` endpoint; verify header `X-Telegram-Bot-Api-Secret-Token` (set via `setWebhook secret_token`) with constant-time compare → else 403.
- Allow-list the owner's Telegram user id (env `TELEGRAM_OWNER_ID`); ignore everyone else silently.
- Reuse the `/calendar/week` logic (refactor into a function) and format a readable Hebrew message per day (RTL-friendly, no tables).
- New secrets: `telegram-bot-token`, `telegram-webhook-secret` (generated). Grant Secret Accessor per secret. That brings active secret versions to 6 (free-tier limit).
- Owner steps: create bot with @BotFather (`/newbot`), get token; get own user id (e.g. @userinfobot); store secrets; call `setWebhook` with `url=<service URL>/telegram/webhook` and `secret_token`.
- Always return 200 to Telegram quickly (it retries on errors); log failures redacted.
- Tests: webhook rejects bad secret, ignores non-owner, formats a week.
