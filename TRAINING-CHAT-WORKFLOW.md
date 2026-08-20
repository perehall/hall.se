# Träningscoach – stående arbetsregel

Den här filen dokumenterar hur ChatGPT ska arbeta med träningssystemet i `perehall/hall.se`.

## Manuell hämtning från chatten

När användaren i träningschatten skriver exempelvis:

- `hämta senaste passet`
- `hämta passet`
- `kolla Strava`
- `uppdatera planen`

ska ChatGPT **inte vänta på nästa 3-timmarskörning** och inte leta efter en separat Strava-plugin.

ChatGPT ska i stället trigga den manuella synken genom att uppdatera:

`träning/data/manual-sync-trigger.txt`

Workflowen `.github/workflows/update-training.yml` lyssnar på push till den filen och kör då samma fulla pipeline direkt:

`Strava → activities.json → AI-coach → eventuell konservativ planjustering → build.py → index.html`

Efter körningen ska ChatGPT verifiera att den nya aktiviteten finns i `träning/data/activities.json`, läsa coachutfallet i `träning/data/coach.json` och använda den faktiska uppdaterade planen i `träning/data/plan.json`.

## Automatisk fallback

Samma workflow körs dessutom schemalagt var tredje timme enligt:

`17 */3 * * *`

Den schemalagda körningen är automatik/fallback. Vid uttrycklig begäran i chatten ska den manuella vägen användas direkt.

## Grundprincip

Träningschatten är en aktiv kontrollpunkt för systemet. Den ska kunna hämta färska Strava-data och uppdatera den levande träningsplanen härifrån, inte bara läsa tidigare batchdata.
