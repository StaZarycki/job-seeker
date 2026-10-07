# Job Seeker – frontend

Aplikacja webowa do przeglądania ofert dopasowanych do CV. Odtwarza design „Job Seeker – web app” (ciemny i jasny motyw) i korzysta wyłącznie z REST API backendu.

## Uruchomienie

```bash
npm install
npm run dev        # http://localhost:5173, wymaga backendu na 127.0.0.1:8000
```

Zapytania pod `/api/*` serwer Vite przekazuje do backendu (`vite.config.ts`). Inny adres backendu ustawisz zmienną `JOBSEEKER_API=http://host:port`.

## Skrypty

| Skrypt | Działanie |
|---|---|
| `npm run dev` / `build` / `preview` | serwer deweloperski / build produkcyjny / podgląd buildu |
| `npm run typecheck` | TypeScript (tryb strict) |
| `npm run lint` | oxlint |
| `npm test` | Vitest + Testing Library + MSW (API zamockowane) |
| `npm run format` | Prettier |
| `npm run gen:api` | eksport OpenAPI z backendu i wygenerowanie `src/api/schema.ts` |

## Struktura

```
src/
  api/          client.ts (fetch, błędy z kodami z backendu), hooks.ts (TanStack Query), schema.ts (generowane)
  app/          router, AppShell (menu boczne ≥768 px / dolne zakładki na telefonie), motyw
  components/   wspólne elementy UI: wynik, chipy umiejętności, paski składowych, PresetPicker, stany błędów
  features/     offers, profile, searches, sources – ekrany z designu
  lib/          formatowanie (PLN, liczebniki, daty), media queries
  styles/       tokeny kolorów (dark/light), style globalne, scrollbary
```

## Zachowanie zależne od szerokości ekranu

| Szerokość | Nawigacja | Szczegóły oferty |
|---|---|---|
| ≥ 1200 px | menu boczne | panel obok listy |
| 768–1199 px | menu boczne | panel wysuwany z prawej |
| < 768 px | dolne zakładki | osobny ekran z paskiem „Zapisz / Aplikuj” |

Na telefonie wybór wyszukiwania i edycja filtrów otwierają się jako panele od dołu ekranu.

Stan widoku jest w adresie URL, np. `/?search=cpp&mode=ai` albo `/offers/<id>`. Linki można kopiować, a przycisk wstecz działa.
