# Job Seeker – backend

The application's backend (the frontend lives in [`../web`](../web/README.md)). Run all commands below from the `backend/` directory.

The app finds job offers that match your CV. It downloads offers from job boards (JustJoin.it for now), builds a profile from your PDF CV and ranks the offers with an explanation for each. It has two modes:

- **`basic`** (default, called "Standard" in the UI): rule-based scoring. Needs no API key and costs nothing.
- **`ai`**: the best offers from the rule-based ranking are also assessed by an AI model. Claude Haiku 4.5 by default.

CLI output and API error messages are in Polish.

## Quick start

```bash
uv sync                                   # install dependencies
cp config.example.toml config.toml        # optional: adjust your preferences
mkdir cv                                  # put your PDF CV here (any file name)
uv run jobseeker profile show             # preview the profile built from the CV
uv run jobseeker sync                     # download offers into the local database (~20 s)
uv run jobseeker match --top 20           # ranking (basic mode)
uv run jobseeker match -n 10 --details    # with the score broken down into components
```

AI mode needs an API key. Copy `.env.example` to `.env`, set `ANTHROPIC_API_KEY`, then run:

```bash
uv run jobseeker match --mode ai                          # Haiku 4.5, assesses the top 20 offers
uv run jobseeker match --mode ai --model claude-sonnet-5-5
```

AI assessments are cached per profile version and per model, so running again sends no requests to the model.

Other commands: `jobseeker categories` (category keys for the config), `jobseeker offer <id>` (full offer description), `jobseeker serve` (REST API, docs at http://127.0.0.1:8000/docs).

## REST API

`uv run jobseeker serve` starts the API used by the frontend. Full, up-to-date documentation is at `/docs`.

| Endpoint | Description |
|---|---|
| `GET /matches?search=&mode=&top=&status=&activity=` | ranked offers (Standard or AI) with filters; `activity=unvisited` leaves out visited offers, `activity=applied` returns the ones marked as applied |
| `GET /offers/{id}`, `PUT /offers/{id}/status`, `POST /offers/{id}/assess` | details with description, save/hide, AI assessment of a single offer |
| `PUT /offers/{id}/activity` | "visited" (`visited`) and "applied" (`applied`) marks |
| `GET /profile`, `POST /profile/cv`, `POST /profile/rebuild`, `GET/PUT /profile/overrides` | profile built from the CV and manual corrections |
| `GET /searches`, `GET /preferences`, `GET /settings` | search presets with offer counts, preferences, settings for the UI |
| `GET /sources`, `GET /sources/{source}/categories` | source status and categories |
| `POST /sync`, `GET /sync/status`, `DELETE /sync`, `GET /syncs` | background sync with progress, cancellation, history |

Errors look like `{"detail": "...", "code": "..."}`. Example codes: `cv_not_found`, `ai_not_configured`, `source_unavailable`, `sync_in_progress`.

To allow browser access from origins other than the frontend dev server, set `[api] cors_origins`. Anthropic API keys that belong to an organization without a workspace need `ANTHROPIC_WORKSPACE_ID` in `.env`.

## Changing your CV

Put the new PDF in `cv/`. You can delete the old one, but you don't have to: the newest file wins and the name doesn't matter.

- On the next run the app detects the change by its SHA-256 checksum and rebuilds the profile by itself.
- Old AI assessments stop being used, and downloaded offers don't need to be fetched again.
- Manual profile corrections go in `profile.overrides.toml` (template: `profile.overrides.example.toml`). They survive a CV change.
- A new CV can also be uploaded through the API: `POST /profile/cv`.

## Areas and switching technologies

Experience is computed **for each offer separately**, in the offer's main technologies. Years from positions in your CV are attributed to the technologies mentioned in them (`jobseeker profile show` shows the result), and general experience carries over partially (`transfer_ratio`).

Example: with 4 years of experience, 3 of them in Node.js, a Node.js offer means ~3.4 years, i.e. mid level, and a C++ offer ~1.4 years, i.e. junior. With `experience_levels = "auto"`, offers at your level and one level up pass: junior/mid in C++ and mid/senior in Node.js.

You choose the area with a search preset from `config.toml`:

```bash
uv run jobseeker searches                 # list presets
uv run jobseeker sync --search cpp        # download the preset's categories
uv run jobseeker match --search cpp -d    # C++ ranking (junior/mid offers, C++ as the target)
```

`target_skills` are the technologies you are moving towards: they get partial credit in matching and are passed to the AI model. AI assessments are cached separately for each search preset.

## Matching

1. **Hard filters** from `[search]`: experience level (automatic or a fixed list), workplace type, on-site/hybrid only in preferred cities, excluded keywords.
2. **Rule score 0–100**: a weighted sum of components. Set the weights in `[matching.weights]`.

   | Component | What it measures |
   |---|---|
   | skills | coverage of required skills, weighted by their level; aliases and related technologies count partially |
   | title | whether the job title matches the role you are looking for |
   | seniority | the required level compared with your experience in the offer's technologies |
   | location | remote work or a preferred city |
   | salary | pay compared with your expected minimum |
   | languages | required languages and levels |
   | freshness | how long ago the offer was published |

3. **`ai` mode**: the `top_n` best offers are sent to the model together with their full descriptions. The model returns a score, pros, cons and missing skills. The final score is `weight · AI + (1 − weight) · rules`.

The model receives the profile and the CV text **without** email, phone number, links and the header with your name.

## Architecture

```
src/job_seeker/
  domain/models.py        source-agnostic models (JobOffer, CandidateProfile, MatchResult…)
  sources/                job board integrations: base.py (JobSource protocol) + registry.py
    justjoin/             JustJoin.it API client + JSON → JobOffer mapper
  profile/                CV → profile: PDF reading, skill dictionary, change detection, overrides
  matching/
    rules.py              filters + rule-based scoring
    ai/                   pluggable AI providers (anthropic, openai_compatible) with a shared prompt
    pipeline.py           filters → rules → [AI] → ranking
  storage/db.py           SQLite: offers, AI assessment cache, sync history
  services/job_seeker.py  application logic shared by the CLI and the API
  cli.py, api/            interfaces
```

### Adding a job board

1. Create `sources/<name>/` with a class implementing `JobSource` (`fetch_offers`, `fetch_details`, `list_categories`, `aclose`) that maps the board's data to `JobOffer`.
2. Register it in `sources/registry.py` (`register("<name>", factory)`).
3. Add the name to `search.sources` in `config.toml`.

Matching, caching, the CLI and the API work without further changes.

### Another AI model

- **Claude:** just change `ai.model`.
- **Other providers** (OpenAI, OpenRouter, local Ollama or LM Studio): `uv sync --extra openai`, then set `provider = "openai_compatible"`, `model` and, if needed, `base_url` in the config.
- **Your own provider:** implement `AIScorer` in `matching/ai/` and add it to `matching/ai/registry.py`.

## Development

```bash
uv sync --all-extras
uv run pytest
uv run ruff check . && uv run ruff format .
uv run mypy src tests
```
