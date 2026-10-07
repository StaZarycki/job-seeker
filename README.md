# Job Seeker

Szuka ofert pracy pasujących do Twojego CV. Pobiera oferty z serwisów (na razie JustJoin.it), buduje profil z CV w PDF i układa ranking z uzasadnieniem. Ocenia regułami (tryb Standard, darmowy) albo dodatkowo modelem AI.

| Część | Katalog | Technologie |
|---|---|---|
| Backend: profil z CV, pobieranie ofert, dopasowanie, REST API i CLI | [`backend/`](backend/README.md) | Python 3.13, FastAPI, SQLite, uv |
| Frontend: aplikacja webowa (desktop, tablet, telefon) | [`web/`](web/README.md) | React 19, TypeScript, Vite, TanStack Query |

## Uruchomienie

```bash
cd backend
uv sync
uv run jobseeker serve        # API na http://127.0.0.1:8000 (dokumentacja: /docs)
```

W drugim terminalu:

```bash
cd web
npm install
npm run dev                   # aplikacja na http://localhost:5173
```

Frontend wysyła zapytania pod `/api/...`, a serwer deweloperski Vite przekazuje je do backendu na porcie 8000.

Pierwsze kroki w aplikacji:
1. Wrzuć CV (PDF) do `backend/cv/` albo wgraj je na ekranie **Profil**.
2. Pobierz oferty na ekranie **Źródła** lub przyciskiem **Synchronizuj** na ekranie **Oferty**.

Z backendu można też korzystać bez frontendu, przez CLI (`uv run jobseeker --help`), co opisuje [backend/README.md](backend/README.md).

## Rozwój

```bash
# backend
cd backend && uv run pytest && uv run ruff check . && uv run mypy src tests

# frontend
cd web && npm run typecheck && npm run lint && npm test

# po zmianie API: wygeneruj typy TypeScript z OpenAPI backendu
cd web && npm run gen:api
```

## Licencja

[MIT](LICENSE)
