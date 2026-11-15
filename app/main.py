"""AI Chief of Staff - service entry point.

Endpoints
  GET /healthz                 process is up
  GET /readyz                  database reachable
  GET /oauth/google/start      owner starts Google Calendar consent (requires ?key=ADMIN_API_KEY)
  GET /oauth/google/callback   Google redirects here with an auth code
  GET /calendar/week           events for the next 7 days, grouped by day (requires X-Admin-Key)
"""
import logging
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import FastAPI, Header, HTTPException, Query, Response
from fastapi.responses import HTMLResponse, RedirectResponse

from app import db, security
from app.calendar import google
from app.config import GOOGLE_SCOPES, get_settings

# Cloud Run collects stdout; JSON lines become structured logs with severity.
logging.basicConfig(
    level=logging.INFO,
    format='{"severity":"%(levelname)s","logger":"%(name)s","message":"%(message)s"}',
)
log = logging.getLogger("cos")

app = FastAPI(title="AI Chief of Staff", version="0.2.0")


def _redact(text: str) -> str:
    """Strip credentials from error text before logging (URLs and key=value forms)."""
    text = re.sub(r"(postgres(?:ql)?://)[^@\s]*@", r"\1***@", text)
    return re.sub(r"(password\s*=\s*)\S+", r"\1***", text, flags=re.IGNORECASE)


def _http_client() -> httpx.Client:
    return httpx.Client(timeout=15)


# ---------------------------------------------------------------- health


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@app.get("/readyz")
def readyz(response: Response) -> dict:
    url = get_settings().database_url
    if not url:
        response.status_code = 503
        return {"status": "error", "db": "DATABASE_URL is not set"}
    try:
        with db.connect(url) as conn:
            conn.execute("SELECT 1")
        return {"status": "ok", "db": "ok"}
    except Exception as exc:
        log.error("database check failed: %s: %s", type(exc).__name__, _redact(str(exc)))
        response.status_code = 503
        return {"status": "error", "db": "unreachable"}


# ---------------------------------------------------------------- Google OAuth


def _require_oauth_config():
    s = get_settings()
    if not s.google_oauth_configured or not s.database_url:
        raise HTTPException(status_code=503, detail="Google Calendar integration is not configured yet")
    return s


@app.get("/oauth/google/start")
def oauth_start(key: str = Query(default="")):
    s = _require_oauth_config()
    if not security.constant_time_equals(key, s.admin_api_key):
        # Only the owner may connect a calendar; otherwise anyone could overwrite the stored token.
        raise HTTPException(status_code=403, detail="Forbidden")
    state = security.sign_state(s.token_encryption_key)
    return RedirectResponse(google.build_auth_url(s.google_client_id, s.oauth_redirect_uri, GOOGLE_SCOPES, state))


@app.get("/oauth/google/callback", response_class=HTMLResponse)
def oauth_callback(code: str = Query(default=""), state: str = Query(default=""), error: str = Query(default="")):
    s = _require_oauth_config()
    if error:
        log.warning("google consent returned error: %s", error)
        raise HTTPException(status_code=400, detail=f"Google returned: {error}")
    if not security.verify_state(s.token_encryption_key, state):
        raise HTTPException(status_code=400, detail="Invalid or expired state")
    with _http_client() as client:
        tokens = google.exchange_code(client, s.google_client_id, s.google_client_secret, s.oauth_redirect_uri, code)
    refresh = tokens.get("refresh_token")
    if not refresh:
        raise HTTPException(status_code=400, detail="Google did not return a refresh token; retry the connect link")
    db.init_schema(s.database_url)
    db.save_refresh_token(
        s.database_url, "google", security.encrypt(s.token_encryption_key, refresh), tokens.get("scope", "")
    )
    log.info("google calendar connected, scopes=%s", tokens.get("scope", ""))
    return "<h2>Google Calendar connected.</h2><p>You can close this tab.</p>"


# ---------------------------------------------------------------- Calendar


@app.get("/calendar/week")
def calendar_week(x_admin_key: str = Header(default="")) -> dict:
    s = _require_oauth_config()
    if not security.constant_time_equals(x_admin_key, s.admin_api_key):
        raise HTTPException(status_code=403, detail="Forbidden")
    db.init_schema(s.database_url)
    token_enc = db.load_refresh_token(s.database_url, "google")
    if not token_enc:
        raise HTTPException(status_code=409, detail="Google Calendar not connected; open /oauth/google/start first")
    refresh = security.decrypt(s.token_encryption_key, token_enc)

    start = datetime.now(timezone.utc)
    end = start + timedelta(days=7)
    with _http_client() as client:
        access = google.refresh_access_token(client, s.google_client_id, s.google_client_secret, refresh)
        provider = google.GoogleCalendarProvider(client, access, s.timezone)
        events = provider.list_events(start, end)

    by_day: dict[str, list[dict]] = defaultdict(list)
    for e in events:
        by_day[e.start[:10]].append(
            {"calendar": e.calendar, "title": e.title, "start": e.start, "end": e.end,
             "all_day": e.all_day, "location": e.location}
        )
    return {"from": start.isoformat(), "to": end.isoformat(), "count": len(events), "days": dict(sorted(by_day.items()))}
