# Setup: Telegram bot (COS-33)

One-time setup by the owner. Code is already deployed; until these steps are done,
`POST /telegram/webhook` returns 503. Prerequisite: Google Calendar is connected (COS-22).

How it works: Telegram calls `https://<service>/telegram/webhook` for every message to the bot.
The service checks the `X-Telegram-Bot-Api-Secret-Token` header (403 otherwise), ignores anyone
but `TELEGRAM_OWNER_ID`, and puts the reply in the HTTP response. Because the reply rides on the
webhook response, **the service never needs the bot token** — it is stored in Secret Manager for the
owner (and future proactive messages) but not granted to the runtime service account.

## 1. Create the bot (Telegram app)
- Chat with **@BotFather** → `/newbot` → pick a name and a username ending in `bot`.
- BotFather replies with a token like `123456789:AA...`. Keep the chat open for step 3.
- Optional: `/setprivacy` → Enable (default), `/setjoingroups` → Disable (the bot is for you only).

## 2. Get your own Telegram user id
- Chat with **@userinfobot** → it replies with `Id: 123456789`. This number is not secret.

## 3. Secrets (Cloud Shell)
```bash
gcloud config set project ai-cos-or
SA=838175899464-compute@developer.gserviceaccount.com

# Bot token: paste once, then Enter. Validate the format before storing (lesson #2).
read -s V; echo "length=${#V}"; [[ "$V" =~ ^[0-9]+:[A-Za-z0-9_-]{30,}$ ]] && echo "format OK" || echo "BAD FORMAT - do not store"
```
Only if it printed `format OK`:
```bash
printf '%s' "$V" | gcloud secrets create telegram-bot-token --data-file=- && unset V
```
Webhook secret: generated, never typed (Telegram allows `A-Z a-z 0-9 _ -`, up to 256 chars):
```bash
python3 -c "import secrets;print(secrets.token_urlsafe(32),end='')" | gcloud secrets create telegram-webhook-secret --data-file=-
```
Grant the runtime SA access to the webhook secret **only** (least privilege; it doesn't need the bot token):
```bash
gcloud secrets add-iam-policy-binding telegram-webhook-secret --member="serviceAccount:$SA" --role="roles/secretmanager.secretAccessor"
```
This brings active secret versions to 6 of the 6 free ones.

## 4. Wire into Cloud Run
Replace `YOUR_TELEGRAM_ID` with the number from step 2:
```bash
gcloud run services update ai-chief-of-staff --region europe-west1 --update-env-vars TELEGRAM_OWNER_ID=YOUR_TELEGRAM_ID --update-secrets TELEGRAM_WEBHOOK_SECRET=telegram-webhook-secret:latest
```

## 5. Point Telegram at the service
```bash
TOKEN=$(gcloud secrets versions access latest --secret=telegram-bot-token)
HOOK=$(gcloud secrets versions access latest --secret=telegram-webhook-secret)
curl -s "https://api.telegram.org/bot$TOKEN/setWebhook" \
  -d url=https://ai-chief-of-staff-838175899464.europe-west1.run.app/telegram/webhook \
  -d secret_token="$HOOK" -d allowed_updates='["message"]' -d drop_pending_updates=true; echo
curl -s "https://api.telegram.org/bot$TOKEN/getWebhookInfo"; echo
unset TOKEN HOOK
```
Expect `"ok":true` and, in `getWebhookInfo`, the URL with no `last_error_message`.

## 6. Verify (acceptance criteria)
1. Send `/week` to the bot → a Hebrew message with this calendar week (Sunday–Saturday), grouped by day.
2. Send any other text → the same reply.
3. From another Telegram account (ask a friend) → no reply at all.
4. `curl -s -o /dev/null -w '%{http_code}\n' -X POST https://ai-chief-of-staff-838175899464.europe-west1.run.app/telegram/webhook -H 'Content-Type: application/json' -d '{}'` → `403`.

If the bot says the Google connection expired: reconnect via `/oauth/google/start?key=...`
(Testing-mode refresh tokens last 7 days — COS-36).
