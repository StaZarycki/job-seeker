# CLAUDE.md

Job Seeker matches job offers (JustJoin.it for now) to the user's CV. Two independent parts in one repo:

- `backend/`: Python 3.13, FastAPI, SQLite, uv. The CLI (`jobseeker`) and the REST API share one service layer.
- `web/`: React 19, TypeScript (strict), Vite, TanStack Query, CSS Modules. It talks only to the REST API.

The user writes in Polish. All UI copy, CLI output and user-facing error messages are in Polish. Code, comments and commit messages are in English.

## Commands

Run each part from its own directory.

```bash
# backend/
uv sync --all-extras                     # first setup (extras: openai_compatible scorer)
uv run jobseeker serve                   # API on 127.0.0.1:8000, docs at /docs
uv run jobseeker sync | match | profile show | searches | categories
uv run pytest
uv run ruff check . && uv run ruff format .
uv run mypy src tests                    # strict

# web/
npm install
npm run dev                              # localhost:5173, proxies /api/* -> 127.0.0.1:8000 (strips /api)
npm run typecheck                        # tsc -b
npm run lint                             # oxlint
npm test                                 # vitest + Testing Library + MSW
npm run format                           # prettier (printWidth 120, single quotes)
npm run gen:api                          # export backend OpenAPI -> web/openapi.json -> src/api/schema.ts
```

`.claude/launch.json` defines the `backend` and `web` preview servers.

Before finishing a change, all checks for the touched part must pass:
- backend: pytest, ruff, mypy;
- web: typecheck, lint, test, prettier `--check`.

## Rules that matter

- **API contract.** After changing any backend model or route that the frontend uses, run `npm run gen:api` in `web/` and commit the regenerated `openapi.json` and `src/api/schema.ts`. Never hand-edit `schema.ts`. Response models inherit from `job_seeker.domain.models.Model` (`json_schema_serialization_defaults_required`), so generated TS types have no spurious optional fields. Keep using it for new response models.
- **Errors.** The API returns `{"detail": "<Polish message>", "code": "<code>"}`. Codes are mapped in `backend/src/job_seeker/api/app.py` (`ERRORS`) and mirrored in `web/src/api/client.ts` (`ApiErrorCode`). The UI picks its state from `code`, never from the message text.
- **Personal data.** Never commit `backend/cv/`, `backend/data/`, `backend/.env`, `backend/config.toml` or `backend/profile.overrides.toml`; all are gitignored. Never put CV contact data into anything sent to an AI model: `cv_reader.sanitize` strips it.
- **AI calls cost money.** `mode=ai` sends real requests to Anthropic using the user's key from `backend/.env`. Don't trigger AI mode (CLI `--mode ai`, `/matches?mode=ai`, `/offers/{id}/assess`) without asking. Tests use `tests/fakes.py::FakeScorer` and never touch the network. Default model: `claude-haiku-4-5`. Keys without a workspace need `ANTHROPIC_WORKSPACE_ID`.
- **Don't edit the user's config.** `backend/config.toml` and `profile.overrides.toml` belong to the user. Change `config.example.toml` / `profile.overrides.example.toml` instead, and tell the user what to copy.
- **uv workspace trap.** On the author's machine a parent directory holds a `pyproject.toml` uv workspace. Running `uv init` here once added this project to its `members`, so never run `uv init`. `backend/` works standalone with `uv sync`.

## Backend architecture (`backend/src/job_seeker/`)

- `domain/models.py`: source-agnostic models (`JobOffer`, `CandidateProfile`, `RuleScore`, `MatchResult`, …). `JobOffer.id` = `source:external_id` (a computed field, so it appears in API output).
- `config.py`: `config.toml` → `AppConfig`.
  - `[search]` is the default search; `[searches.<name>]` are presets merged on top via `AppConfig.preferences(search, overrides)`.
  - `SearchPreferences` forbids unknown keys, so typos fail loudly.
- `sources/`: the `JobSource` protocol (`fetch_offers(query, on_progress)`, `fetch_details`, `list_categories`) and the registry.
  - JustJoin uses the undocumented `justjoin.it/api/candidate-api`. `from` / `to` amounts are already monthly PLN; pagination uses `from` + `itemsCount` (`perPage` is ignored).
  - To add a job board: a new module plus one `register()` call in `sources/registry.py`.
- `profile/`: CV PDF → `CandidateProfile`.
  - The newest PDF in `cv/` wins.
  - The profile is rebuilt automatically when the CV's SHA-256 or `PARSER_VERSION` changes (bump it when CV parsing changes).
  - `skill_years` is derived from Experience positions; overrides are applied on every load.
- `matching/`:
  - `rules.py`: hard filters plus a weighted 0–100 score with Polish notes.
  - `experience.py`: experience in the offer's main technologies. Untargeted experience transfers at `transfer_ratio`; the `"auto"` level filter allows your level plus one step up.
  - `pipeline.py`: rules first, then the AI for the top N. The AI cache is keyed by `assessment_key` (profile hash + target skills + experience config + provider + model).
  - `ai/`: pluggable scorers with a shared prompt.
- `services/job_seeker.py`: everything the CLI and API call: matching, background sync job (`start_sync_job` / `sync_status` / `cancel_sync`), offer marks (saved/hidden), offer activity (visited/applied), single-offer assessment, search summaries.
- `storage/db.py`: SQLite with short-lived connections per operation. Tables: `offers`, `offer_status` (saved/hidden), `offer_activity` (visited/applied timestamps, independent of the status), `ai_assessments`, `sync_runs`. Schema changes need an in-place migration in `Database.__init__` (see the `categories` column).

Tests live in `backend/tests/`:
- recorded JustJoin fixtures in `tests/fixtures/`;
- `respx` for HTTP;
- `make_pdf()` in `conftest.py` builds real PDFs for CV tests;
- `FakeSource` / `FakeScorer` in `fakes.py`.

## Frontend architecture (`web/src/`)

- `api/client.ts` (fetch wrapper, `ApiError`, type aliases from the schema) and `api/hooks.ts` (all TanStack Query hooks and mutations, with invalidation).
- `app/`:
  - `routes.tsx` defines the routes: `/`, `/offers/:offerId`, `/profile`, `/searches`, `/sources`;
  - `AppShell.tsx`: sidebar on ≥768 px, bottom tabs on phones;
  - `theme.ts`: dark is the default; the choice is stored in localStorage.
- `features/<screen>/`: one folder per screen, each with its own CSS module.
  - Offer list state (preset, mode, filter overrides, status, activity) lives in URL search params (`features/offers/params.ts`).
  - Opening "Aplikuj w JustJoin.it" marks the offer as visited (`useSetOfferActivity`, patched optimistically); "applied" is a manual toggle in the offer details. Visited cards are dimmed.
- `components/`: shared UI (`ui.tsx`, `PresetPicker`, `ApiErrorState`, `icons.tsx` with inline SVGs from the design).
- `styles/tokens.css`: design tokens as CSS variables for dark and light. Use `var(--…)`, never hard-coded colors.

Responsive behaviour follows the design:

| Width | Navigation | Offer details |
|---|---|---|
| ≥ 1200 px | sidebar | side panel next to the list |
| 768–1199 px | sidebar | drawer from the right |
| < 768 px | bottom tabs | full screen with a sticky action bar |

On phones, the preset picker and filter editors are bottom sheets. Use `useMediaQuery(PHONE_QUERY | WIDE_QUERY)` from `lib/hooks.ts` when markup must differ; otherwise prefer CSS.

Conventions:
- CSS Modules: wrap global classes in `:global(.btn)`.
- No non-component exports from component files (Fast Refresh, oxlint): put helpers in `lib/`.
- Derive state instead of setting it in effects (oxlint `set-state-in-effect`).
- Touch targets are ≥ 44 px on phones.
- Use real `<button>` / `<a>` elements with `aria-*`.
- Tests render the whole app through `test/render.tsx::renderApp(path, { width })`. Mock the API with MSW using `test/fixtures.ts::baseHandlers()` plus per-test handlers. `window.innerWidth` drives the `matchMedia` stub in `test/setup.ts`.

## Design

The approved design is a private claude.ai Design artifact: https://claude.ai/artifact/QV2ds5FaNiGfxz42rQfyNA. It holds 5 desktop screens, 5 phone screens and a states sheet. Desktop and phone versions were deliberately aligned (labels, data shown, actions). Keep them consistent when changing UI.

Naming used in the UI:
- the rules mode is called **Standard**, not "reguły" or "basic";
- the default preset is **Domyślne**.
