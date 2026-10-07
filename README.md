# Job Seeker

Finds job offers that match your CV. It downloads offers from job boards (JustJoin.it for now), builds a profile from your PDF CV and ranks the offers with an explanation for each. Offers are scored by rules (Standard mode, free) or additionally by an AI model.

The user interface and messages are in Polish.

| Part | Directory | Stack |
|---|---|---|
| Backend: CV profile, offer download, matching, REST API and CLI | [`backend/`](backend/README.md) | Python 3.13, FastAPI, SQLite, uv |
| Frontend: web app (desktop, tablet, phone) | [`web/`](web/README.md) | React 19, TypeScript, Vite, TanStack Query |

## Getting started

```bash
cd backend
uv sync
uv run jobseeker serve        # API on http://127.0.0.1:8000 (docs: /docs)
```

In a second terminal:

```bash
cd web
npm install
npm run dev                   # app on http://localhost:5173
```

The frontend sends requests to `/api/...`, and the Vite dev server forwards them to the backend on port 8000.

First steps in the app:
1. Put your CV (PDF) in `backend/cv/` or upload it on the **Profil** (Profile) screen.
2. Download offers on the **Źródła** (Sources) screen or with the **Synchronizuj** (Sync) button on the **Oferty** (Offers) screen.

You can also use the backend without the frontend, through the CLI (`uv run jobseeker --help`), as described in [backend/README.md](backend/README.md).

## Development

```bash
# backend
cd backend && uv run pytest && uv run ruff check . && uv run mypy src tests

# frontend
cd web && npm run typecheck && npm run lint && npm test

# after an API change: generate TypeScript types from the backend's OpenAPI schema
cd web && npm run gen:api
```

## License

[MIT](LICENSE)
