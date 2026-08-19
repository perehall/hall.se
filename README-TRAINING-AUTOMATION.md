# Träningsautomation

Flöde: Garmin → Strava → GitHub Actions → `träning/data/activities.json` → `träning/scripts/build.py` → preview i `träning/index.generated.html`.

Den befintliga `träning/index.html` lämnas orörd tills Strava-synken är verifierad.

## GitHub Secrets som krävs

- `STRAVA_CLIENT_ID`
- `STRAVA_CLIENT_SECRET`
- `STRAVA_REFRESH_TOKEN`
- `TRAINING_SECRET_PAT`

`TRAINING_SECRET_PAT` används enbart för att spara Stravas senaste roterade refresh token tillbaka som GitHub Secret.

## Säkerhetsprincip

Automatiken får registrera aktivitetsfakta och bygga sidan. Den får inte automatiskt öka träningsbelastningen eller hitta på nya hårda pass. Coachning och planändringar ligger separat i `träning/data/plan.json`.

## Testordning

1. Skapa/konfigurera Strava API-app.
2. Lägg in de fyra secrets ovan i repot.
3. Kör `Actions → Update training data (manual test) → Run workflow`.
4. Kontrollera `träning/data/activities.json` och `träning/index.generated.html`.
5. När detta är verifierat ändras build-output till `träning/index.html` och schemaläggning aktiveras.
