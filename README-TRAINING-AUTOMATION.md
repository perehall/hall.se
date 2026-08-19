# Träningsautomation

Detta repo innehåller ett enkelt, konservativt träningssystem där planering sker tillsammans med ChatGPT och genomförda pass hämtas automatiskt från Strava.

## Översikt

Normal arbetsloop:

`Planering i ChatGPT → plan.json → träning → Garmin → Strava → GitHub Actions → activities.json → AI-coach → ev. konservativ planjustering → index.html`

Live-sidan byggs till:

`träning/index.html`

Den gamla manuella sidan säkerhetskopieras en gång till:

`träning/index.manual-backup.html`

## Hur systemet används

### 1. Planering

Den huvudsakliga träningsplaneringen görs i ChatGPT. Planen kan uppdateras direkt i:

`träning/data/plan.json`

ChatGPT kan också manuellt uppdatera plan, coachregler, scripts och webbsida via GitHub när det behövs.

Planeringen ska vara ett levande upplägg och styras av faktisk belastning och återhämtning, inte mekaniskt följa ett tidigare schema.

### 2. Genomförda pass

Garmin synkar normalt aktiviteter till Strava. GitHub Actions kör sedan Strava-synken och sparar aktivitetsdata i:

`träning/data/activities.json`

Strava används alltså som automatisk datakälla för genomförda pass.

### 3. AI-coach

Efter Strava-synken körs:

`träning/scripts/coach.py`

AI-coachen använder OpenAI API med modellen `gpt-5-mini` och läser bland annat:

- senaste aktiviteten
- relevanta tidigare aktiviteter
- aktuell träningsplan
- föregående och kommande 2–3 dagars belastning
- reglerna i `träning/coach_prompt.md`

Resultatet sparas i:

`träning/data/coach.json`

Analysen ska skilja mellan:

- fakta
- tolkning
- osäkerhet / sådant som inte går att avgöra från data

AI-coachen ska också ge en rekommendation för den närmaste planen.

## Automatisk planändring

AI-coachen får inte fritt skriva om träningsplanen.

Tillåtna beslut är:

- `keep` – behåll planen
- `reduce` – skala ned ett kommande pass
- `rest` – ersätt ett kommande pass med vila eller mycket lätt träning
- `review` – underlaget räcker inte eller förändringen kräver mänskligt beslut

Automatiken får aldrig automatiskt:

- öka volym
- öka intensitet
- lägga till kvalitetspass
- fylla en ledig dag med träning
- hitta på zoner, farter, watt, puls eller återhämtningsstatus

Ökad eller mer specifik belastning beslutas i den vanliga planeringen med ChatGPT.

Enduro räknas som faktisk träningsbelastning och kan ersätta annan träning.

## AI-coachens säkerhetsregler

Coachreglerna finns i:

`träning/coach_prompt.md`

Viktiga principer:

- använd endast data som faktiskt finns
- skilj fakta från tolkning
- kontrollera belastningen 2–3 dagar bakåt och framåt
- prioritera kontinuitet och absorberbar belastning
- klassificera inte belastning som hög/låg eller över/under normalt utan personlig baslinje
- använd inte låg puls vid styrketräning som bevis på låg muskulär belastning eller god återhämtning
- använd `high confidence` endast när de viktigaste beslutspåverkande variablerna faktiskt finns i underlaget och pekar åt samma håll
- vid otillräckliga data: var konservativ och redovisa vad som saknas

## Webbsidan

`träning/scripts/build.py` bygger den aktuella live-sidan:

`träning/index.html`

Sidan visar aktuell plan, genomförda pass och AI-coachens bedömningar/rekommendationer.

Tidsstämpeln för "senast uppdaterad" genereras i tidszonen `Europe/Stockholm`.

## GitHub Actions

Workflow:

`.github/workflows/update-training.yml`

Workflowet kan startas manuellt med `workflow_dispatch` och körs dessutom schemalagt:

`17 */3 * * *`

Det innebär en körning var tredje timme.

Nuvarande flöde i workflowet är:

1. Checkout av repot.
2. Python 3.12 installeras.
3. Backup av live-sidan skapas om den saknas.
4. Strava synkas.
5. Stravas roterade refresh token sparas tillbaka som GitHub Secret.
6. AI-coachen körs.
7. Live-sidan byggs.
8. Ändrade data, plan, coach-state och webbsida committas och pushas.

AI-coachen har dessutom en trigger-hash och hoppar över OpenAI-anropet när relevant underlag inte har förändrats.

## GitHub Secrets

Följande repository secrets krävs:

- `STRAVA_CLIENT_ID`
- `STRAVA_CLIENT_SECRET`
- `STRAVA_REFRESH_TOKEN`
- `TRAINING_SECRET_PAT`
- `OPENAI_API_KEY`

`TRAINING_SECRET_PAT` används för att skriva tillbaka Stravas senaste roterade refresh token som GitHub Secret.

`OPENAI_API_KEY` används endast av server-side GitHub Actions för AI-coachningen och ska aldrig lagras i koden eller skickas till klienten.

## Strava OAuth

Strava använder OAuth med `activity:read_all`.

Refresh token roteras av Strava. `sync_strava.py` skriver den nya refresh token till en temporär fil och workflowet uppdaterar därefter repository-secreten `STRAVA_REFRESH_TOKEN` via GitHub CLI.

Detta är verifierat med flera efterföljande workflow-körningar.

## Viktiga filer

- `träning/data/plan.json` – aktuell träningsplan
- `träning/data/activities.json` – importerade Strava-aktiviteter
- `träning/data/coach.json` – AI-analyser och coach-state
- `träning/data/settings.json` – övriga inställningar
- `träning/coach_prompt.md` – regler och metod för AI-coachen
- `träning/scripts/sync_strava.py` – Strava-synk och OAuth-refresh
- `träning/scripts/coach.py` – AI-analys och konservativ automatisk planjustering
- `träning/scripts/build.py` – genererar live-sidan
- `.github/workflows/update-training.yml` – automationen
- `träning/index.html` – live-sidan
- `träning/index.manual-backup.html` – engångsbackup av tidigare live-sida

## Designprincip

Systemet ska vara enkelt och underhållssnålt.

Automationen registrerar fakta och gör begränsade konservativa korrigeringar. Den långsiktiga träningsplaneringen, större förändringar och eventuell ökad belastning styrs fortfarande aktivt i dialog med ChatGPT.

Målet är alltså inte en autonom träningscoach som själv skriver hela programmet, utan en kombination av:

`mänskligt styrd planering + automatisk träningsdata + AI-analys + konservativa skyddsräcken`.
