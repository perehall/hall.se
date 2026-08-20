# Dashboard – datainvarianter

Dashboardens summeringar får aldrig bygga på en annan tidsdefinition än de aktivitetsvärden som visas på dagkorten.

## Kanonisk källa

- Genomförda pass: `träning/data/activities.json`.
- Veckointervall: `week_start`–`week_end` i `träning/data/plan.json`.
- Passtid: `elapsed_time_s`; `moving_time_s` används endast om `elapsed_time_s` saknas.
- Passantal: antal unika aktiviteter i aktuell vecka.
- Träningsdagar: antal unika lokala aktivitetsdatum i aktuell vecka.
- Grenfördelning: samma aktiviteter och samma passtid som totalen.
- Tider visas utan avrundning som `H:MM:SS` eller `M:SS` så synliga delsummeringar kan verifieras exakt.

## Fail-closed

Efter `build.py` kör workflowen `träning/scripts/finalize_dashboard.py`.

Den:

1. räknar om veckans summeringar oberoende från rå aktivitetsdata,
2. skriver `träning/data/dashboard_summary.json` som audit-fil,
3. ersätter dashboardens sammanfattning och grenfördelning med verifierade värden,
4. kontrollerar att grenarnas sekunder exakt summerar till total passtid,
5. kontrollerar dubbla aktivitets-ID,
6. verifierar att de exakta förväntade värdena verkligen finns i den renderade HTML-sidan.

Om någon kontroll misslyckas kastar scriptet fel. GitHub Actions avbryts då före Pages-deploy. En dashboard som inte kan verifieras mot aktivitetsdatan ska alltså inte publiceras.
