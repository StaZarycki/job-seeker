# Job Seeker – frontend

A web app for browsing offers matched to your CV. It recreates the "Job Seeker – web app" design (dark and light themes) and talks only to the backend's REST API. The interface is in Polish.

## Running

```bash
npm install
npm run dev        # http://localhost:5173, needs the backend on 127.0.0.1:8000
```

The Vite server forwards requests under `/api/*` to the backend (`vite.config.ts`). Set a different backend address with `JOBSEEKER_API=http://host:port`.

## Scripts

| Script | What it does |
|---|---|
| `npm run dev` / `build` / `preview` | dev server / production build / preview of the build |
| `npm run typecheck` | TypeScript (strict mode) |
| `npm run lint` | oxlint |
| `npm test` | Vitest + Testing Library + MSW (mocked API) |
| `npm run format` | Prettier |
| `npm run gen:api` | export OpenAPI from the backend and generate `src/api/schema.ts` |

## Structure

```
src/
  api/          client.ts (fetch, errors with codes from the backend), hooks.ts (TanStack Query), schema.ts (generated)
  app/          router, AppShell (sidebar ≥768 px / bottom tabs on phones), theme
  components/   shared UI: score, skill chips, score component bars, PresetPicker, error states
  features/     offers, profile, searches, sources – the screens from the design
  lib/          formatting (PLN, Polish plurals, dates), media queries
  styles/       colour tokens (dark/light), global styles, scrollbars
```

## Behaviour by screen width

| Width | Navigation | Offer details |
|---|---|---|
| ≥ 1200 px | sidebar | panel next to the list |
| 768–1199 px | sidebar | drawer sliding in from the right |
| < 768 px | bottom tabs | separate screen with a "Zapisz / Aplikuj" (Save / Apply) bar |

On phones, choosing a search and editing filters open as bottom sheets.

View state lives in the URL, e.g. `/?search=cpp&mode=ai` or `/offers/<id>`. Links can be copied and the back button works.
