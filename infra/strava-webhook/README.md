# Strava webhook → GitHub Actions

Eventkedja för träningsappen:

`Strava → Cloudflare Worker → GitHub repository_dispatch → update-training.yml → Strava API → normalisering → coach → render → Pages`

## Säkerhets- och tillförlitlighetsmodell

- Webhook-payloaden är **signal**, aldrig träningsdatakälla. GitHub hämtar aktuell aktivitet från Strava API med `object_id`.
- Callback-URL:en har en hemlig path-komponent eftersom Strava inte signerar POST-events.
- Workern validerar dessutom `owner_id` och `subscription_id` innan GitHub får ett event.
- GitHub-token ska vara en dedikerad fine-grained PAT för endast `perehall/hall.se` med **Contents: write**, vilket GitHub kräver för `repository_dispatch`.
- Workern väntar högst 1,5 s på GitHubs `204`. Vid fel returnerar den 503 så att Strava kan retrya. Eventnyckeln är deterministisk och GitHub-synken är idempotent.
- Den befintliga schemalagda Strava-synken behålls som fallback tills webhooken är verifierad end-to-end.

## Cloudflare-konfiguration

Från den här katalogen:

```bash
npm install
npx wrangler login
npx wrangler secret put WEBHOOK_PATH_SECRET
npx wrangler secret put STRAVA_VERIFY_TOKEN
npx wrangler secret put GITHUB_DISPATCH_TOKEN
npx wrangler secret put STRAVA_OWNER_ID
npm run deploy
```

`STRAVA_SUBSCRIPTION_ID` sätts först efter att Strava-subscriptionen skapats:

```bash
npx wrangler secret put STRAVA_SUBSCRIPTION_ID
npm run deploy
```

Callback-URL blir:

`https://<worker-host>/strava/<WEBHOOK_PATH_SECRET>`

`GET /healthz` visar endast om konfigurationen finns, aldrig secret-värden.

## Strava-subscription

Strava tillåter en webhook-subscription per API-applikation. Skapa den först när Workern är deployad och callback-verifieringen fungerar. Använd samma `STRAVA_VERIFY_TOKEN` i subscription-anropet som i Workern.

```bash
curl -X POST https://www.strava.com/api/v3/push_subscriptions \
  -F client_id="$STRAVA_CLIENT_ID" \
  -F client_secret="$STRAVA_CLIENT_SECRET" \
  -F callback_url="$STRAVA_WEBHOOK_CALLBACK_URL" \
  -F verify_token="$STRAVA_VERIFY_TOKEN"
```

Svaret innehåller `id`. Lägg det värdet som Worker-secret `STRAVA_SUBSCRIPTION_ID` och deploya igen.

## Lokal test

```bash
npm test
```

Testerna gör inga nätverksanrop. De verifierar Stravas challenge-handshake, identitetskontroller, exakt GitHub-dispatchpayload och att GitHub-fel ger icke-200 så att Strava kan retrya.
