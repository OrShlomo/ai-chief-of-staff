"""Runtime configuration, read from environment variables.

Secrets (DATABASE_URL, GOOGLE_CLIENT_SECRET, TOKEN_ENCRYPTION_KEY, ADMIN_API_KEY)
are injected by Cloud Run from Secret Manager. Nothing secret lives in the repo.
"""
import os
from dataclasses import dataclass

# Least privilege: COS-22 only needs to READ the calendar.
# Write access (calendar.events) will be requested later, in COS-23.
GOOGLE_SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]


@dataclass(frozen=True)
class Settings:
    database_url: str | None
    google_client_id: str | None
    google_client_secret: str | None
    oauth_redirect_uri: str | None
    token_encryption_key: str | None
    admin_api_key: str | None
    timezone: str

    @property
    def google_oauth_configured(self) -> bool:
        return all(
            [
                self.google_client_id,
                self.google_client_secret,
                self.oauth_redirect_uri,
                self.token_encryption_key,
                self.admin_api_key,
            ]
        )


def get_settings() -> Settings:
    return Settings(
        database_url=os.environ.get("DATABASE_URL"),
        google_client_id=os.environ.get("GOOGLE_CLIENT_ID"),
        google_client_secret=os.environ.get("GOOGLE_CLIENT_SECRET"),
        oauth_redirect_uri=os.environ.get("OAUTH_REDIRECT_URI"),
        token_encryption_key=os.environ.get("TOKEN_ENCRYPTION_KEY"),
        admin_api_key=os.environ.get("ADMIN_API_KEY"),
        timezone=os.environ.get("APP_TIMEZONE", "Asia/Jerusalem"),
    )
