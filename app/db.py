"""Database access (Neon Postgres) and schema bootstrap."""
import psycopg

SCHEMA = """
CREATE TABLE IF NOT EXISTS oauth_tokens (
    provider          text PRIMARY KEY,          -- 'google' (single-user MVP)
    refresh_token_enc bytea NOT NULL,            -- Fernet-encrypted refresh token
    scopes            text NOT NULL,
    updated_at        timestamptz NOT NULL DEFAULT now()
);
"""


def connect(url: str) -> psycopg.Connection:
    return psycopg.connect(url, connect_timeout=10)


def init_schema(url: str) -> None:
    with connect(url) as conn:
        conn.execute(SCHEMA)


def save_refresh_token(url: str, provider: str, token_enc: bytes, scopes: str) -> None:
    with connect(url) as conn:
        conn.execute(
            """
            INSERT INTO oauth_tokens (provider, refresh_token_enc, scopes, updated_at)
            VALUES (%s, %s, %s, now())
            ON CONFLICT (provider) DO UPDATE
              SET refresh_token_enc = EXCLUDED.refresh_token_enc,
                  scopes = EXCLUDED.scopes,
                  updated_at = now()
            """,
            (provider, token_enc, scopes),
        )


def load_refresh_token(url: str, provider: str) -> bytes | None:
    with connect(url) as conn:
        row = conn.execute(
            "SELECT refresh_token_enc FROM oauth_tokens WHERE provider = %s", (provider,)
        ).fetchone()
    return bytes(row[0]) if row else None
