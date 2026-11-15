"""AI Chief of Staff - walking skeleton service (COS-31).

Exposes two endpoints:
  /healthz  - the process is up (no dependencies)
  /readyz   - the service can reach the database (Neon Postgres)
"""
import logging
import os
import re

import psycopg
from fastapi import FastAPI, Response

# Cloud Run collects stdout; JSON lines become structured logs with severity.
logging.basicConfig(
    level=logging.INFO,
    format='{"severity":"%(levelname)s","logger":"%(name)s","message":"%(message)s"}',
)
log = logging.getLogger("cos")

app = FastAPI(title="AI Chief of Staff", version="0.1.0")


def _redact(text: str) -> str:
    """Strip credentials from error text before logging (URLs and key=value forms)."""
    text = re.sub(r"(postgres(?:ql)?://)[^@\s]*@", r"\1***@", text)
    return re.sub(r"(password\s*=\s*)\S+", r"\1***", text, flags=re.IGNORECASE)


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@app.get("/readyz")
def readyz(response: Response) -> dict:
    url = os.environ.get("DATABASE_URL")
    if not url:
        response.status_code = 503
        return {"status": "error", "db": "DATABASE_URL is not set"}
    try:
        with psycopg.connect(url, connect_timeout=10) as conn:
            conn.execute("SELECT 1")
        return {"status": "ok", "db": "ok"}
    except Exception as exc:
        log.error("database check failed: %s: %s", type(exc).__name__, _redact(str(exc)))
        response.status_code = 503
        return {"status": "error", "db": "unreachable"}
