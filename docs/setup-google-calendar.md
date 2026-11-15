# Setup: Google Calendar connection (COS-22)

One-time setup by the owner. Code is already deployed; until these steps are done,
`/calendar/week` and `/oauth/google/*` return 503.

## 1. OAuth consent screen (Google Cloud console)
APIs & Services → OAuth consent screen (Google Auth Platform)
- User type: **External**
- App name: `AI Chief of Staff`, support email: yours
- Scopes: `.../auth/calendar.readonly`
- Test users: your Gmail
- **Publishing status → In production.** In "Testing" mode Google expires refresh
  tokens after 7 days. An unverified app in production shows an "unverified app"
  warning on consent; that is fine for a single owner.

## 2. OAuth client
APIs & Services → Credentials → Create credentials → OAuth client ID
- Type: **Web application**
- Authorized redirect URI:
  `https://ai-chief-of-staff-838175899464.europe-west1.run.app/oauth/google/callback`
- Copy the Client ID (not secret) and Client secret (secret).

## 3. Secrets (Cloud Shell)
```bash
gcloud config set project ai-cos-or
SA=838175899464-compute@developer.gserviceaccount.com

# Google client secret: paste once, then Enter
read -s V && printf '%s' "$V" | gcloud secrets create google-client-secret --data-file=- && unset V

# Token encryption key: a Fernet key (32 random bytes, url-safe base64), generated, never typed
python3 -c "import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode(),end='')" \
  | gcloud secrets create token-encryption-key --data-file=-

# Admin key for owner-only endpoints (generated)
python3 -c "import secrets;print(secrets.token_urlsafe(32),end='')" | gcloud secrets create admin-api-key --data-file=-

for s in google-client-secret token-encryption-key admin-api-key; do
  gcloud secrets add-iam-policy-binding $s --member="serviceAccount:$SA" \
    --role="roles/secretmanager.secretAccessor" >/dev/null && echo "granted $s"
done
```

## 4. Wire them into Cloud Run
```bash
gcloud run services update ai-chief-of-staff --region europe-west1 \
  --update-env-vars GOOGLE_CLIENT_ID=PASTE_CLIENT_ID,OAUTH_REDIRECT_URI=https://ai-chief-of-staff-838175899464.europe-west1.run.app/oauth/google/callback \
  --update-secrets GOOGLE_CLIENT_SECRET=google-client-secret:latest,TOKEN_ENCRYPTION_KEY=token-encryption-key:latest,ADMIN_API_KEY=admin-api-key:latest
```

## 5. Connect and verify
```bash
KEY=$(gcloud secrets versions access latest --secret=admin-api-key)
echo "https://ai-chief-of-staff-838175899464.europe-west1.run.app/oauth/google/start?key=$KEY"
```
Open the printed link in the browser, approve read-only access → "Google Calendar connected."

Then:
```bash
curl -s -H "X-Admin-Key: $KEY" https://ai-chief-of-staff-838175899464.europe-west1.run.app/calendar/week | python3 -m json.tool | head -40
unset KEY
```
