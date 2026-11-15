# AI Chief of Staff

An AI "chief of staff" that manages a manager's time against their goals: weekly time budgets, smart scheduling with conflict detection, and a weekly budget-vs-actual review.

- PRD: https://claude.ai/artifact/8dSzzqmQ41gYV7AFZr2iMs
- Backlog: Jira project `COS`

## Architecture (MVP, see ADR-001 in COS-31)
| Concern | Choice |
| --- | --- |
| Compute | Google Cloud Run (`europe-west1`), project `ai-cos-or` |
| Database | Neon Postgres (AWS Frankfurt), free plan |
| Secrets | Google Secret Manager (`neon-database-url` → env `DATABASE_URL`) |
| Scheduled jobs | Google Cloud Scheduler |
| Deploy | Push to `main` → Cloud Build → Cloud Run |

## Endpoints
- `GET /healthz` – process is up
- `GET /readyz` – database reachable

## Run tests locally
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```

## Secrets
Never commit secrets. `DATABASE_URL` is injected at runtime from Secret Manager.
