# Job Seeker – backend

Backend aplikacji (frontend jest w [`../web`](../web/README.md)). Wszystkie komendy poniżej uruchamiasz w katalogu `backend/`.

Aplikacja szuka ofert pracy pasujących do Twojego CV. Pobiera oferty z serwisów (na razie JustJoin.it), buduje profil z CV w PDF i układa ranking ofert z uzasadnieniem. Działa w dwóch trybach:

- **`basic`** (domyślny): ocena na podstawie reguł. Nie wymaga klucza API i nic nie kosztuje.
- **`ai`**: najlepsze oferty z rankingu regułowego ocenia dodatkowo model AI. Domyślnie to Claude Haiku 4.5.

## Szybki start

```bash
uv sync                                   # instalacja zależności
cp config.example.toml config.toml        # opcjonalnie: dostosuj preferencje
mkdir cv                                  # wrzuć tu CV w PDF (nazwa dowolna)
uv run jobseeker profile show             # podgląd profilu zbudowanego z CV
uv run jobseeker sync                     # pobranie ofert do lokalnej bazy (~20 s)
uv run jobseeker match --top 20           # ranking (tryb basic)
uv run jobseeker match -n 10 --details    # z rozbiciem wyniku na składowe
```

Tryb AI wymaga klucza API. Skopiuj `.env.example` do `.env`, wpisz `ANTHROPIC_API_KEY`, a potem uruchom:

```bash
uv run jobseeker match --mode ai                          # Haiku 4.5, ocena top 20 ofert
uv run jobseeker match --mode ai --model claude-sonnet-5-5
```

Oceny AI są zapisywane w cache dla każdej wersji profilu i każdego modelu, więc ponowne uruchomienie nie wysyła zapytań do modelu.

Inne komendy: `jobseeker categories` (klucze kategorii do configu), `jobseeker offer <id>` (pełny opis oferty), `jobseeker serve` (REST API, dokumentacja pod http://127.0.0.1:8000/docs).

## REST API

`uv run jobseeker serve` uruchamia API, z którego korzysta frontend. Pełna, aktualna dokumentacja jest pod `/docs`.

| Endpoint | Opis |
|---|---|
| `GET /matches?search=&mode=&top=&status=` | ranking ofert (Standard lub AI), z filtrami |
| `GET /offers/{id}`, `PUT /offers/{id}/status`, `POST /offers/{id}/assess` | szczegóły z opisem, Zapisz/Ukryj, ocena AI jednej oferty |
| `GET /profile`, `POST /profile/cv`, `POST /profile/rebuild`, `GET/PUT /profile/overrides` | profil z CV i ręczne poprawki |
| `GET /searches`, `GET /preferences`, `GET /settings` | profile wyszukiwania z liczbą ofert, preferencje, ustawienia dla UI |
| `GET /sources`, `GET /sources/{source}/categories` | status źródeł i kategorie |
| `POST /sync`, `GET /sync/status`, `DELETE /sync`, `GET /syncs` | synchronizacja w tle z postępem, przerwanie, historia |

Błędy mają postać `{"detail": "...", "code": "..."}`. Przykładowe kody: `cv_not_found`, `ai_not_configured`, `source_unavailable`, `sync_in_progress`.

Dostęp z przeglądarki z innych adresów niż serwer deweloperski frontendu ustawisz w `[api] cors_origins`. Klucze API Anthropic przypisane do organizacji (bez workspace) wymagają `ANTHROPIC_WORKSPACE_ID` w `.env`.

## Zmiana CV

Wrzuć nowy PDF do `cv/`. Stary możesz usunąć, ale nie musisz, bo liczy się najnowszy plik, a nazwa nie ma znaczenia.

- Przy kolejnym uruchomieniu aplikacja wykrywa zmianę po sumie kontrolnej SHA-256 i sama przebudowuje profil.
- Stare oceny AI przestają być używane, a pobranych ofert nie trzeba ściągać ponownie.
- Ręczne poprawki profilu wpisujesz w `profile.overrides.toml` (wzór: `profile.overrides.example.toml`). Przetrwają podmianę CV.
- Nowe CV można też wgrać przez API: `POST /profile/cv`.

## Obszary i zmiana technologii

Doświadczenie liczone jest **dla każdej oferty osobno**, w jej głównych technologiach. Lata z pozycji w CV przypisywane są technologiom w nich wymienionym (`jobseeker profile show` pokazuje wynik), a ogólny staż przenosi się częściowo (`transfer_ratio`).

Przykład: przy 4 latach stażu, w tym 3 w Node.js, oferta Node.js oznacza ~3,4 roku, czyli poziom mid, a oferta C++ ~1,4 roku, czyli junior. Przy `experience_levels = "auto"` przechodzą oferty na Twoim poziomie i jeden wyżej, czyli junior/mid w C++ i mid/senior w Node.js.

Obszar wybierasz profilem wyszukiwania z `config.toml`:

```bash
uv run jobseeker searches                 # lista profili
uv run jobseeker sync --search cpp        # pobranie kategorii z profilu
uv run jobseeker match --search cpp -d    # ranking dla C++ (oferty junior/mid, C++ jako cel)
```

`target_skills` oznacza technologie, w których kierunku idziesz: są częściowo zaliczane w dopasowaniu i przekazywane modelowi AI. Oceny AI są zapisywane osobno dla każdego profilu wyszukiwania.

## Dopasowanie

1. **Filtry twarde** z `[search]`: poziom doświadczenia (automatyczny albo stała lista), tryb pracy, praca stacjonarna/hybrydowa tylko w preferowanych miastach, wykluczone słowa kluczowe.
2. **Wynik regułowy 0–100**: ważona suma składowych. Wagi ustawisz w `[matching.weights]`.

   | Składowa | Co ocenia |
   |---|---|
   | umiejętności | pokrycie wymaganych umiejętności ważone ich poziomem; aliasy i technologie pokrewne liczą się częściowo |
   | tytuł | czy tytuł stanowiska pasuje do szukanej roli |
   | seniority | wymagany poziom w porównaniu z Twoim doświadczeniem w technologiach oferty |
   | lokalizacja | praca zdalna albo preferowane miasto |
   | widełki | wynagrodzenie względem oczekiwanego minimum |
   | języki | wymagane języki i poziomy |
   | świeżość | jak dawno opublikowano ofertę |

3. **Tryb `ai`**: `top_n` najlepszych ofert trafia do modelu razem z pełnym opisem. Model zwraca wynik, plusy, minusy i brakujące umiejętności. Wynik końcowy to `weight · AI + (1 − weight) · reguły`.

Do modelu trafia profil i tekst CV **bez** e-maila, telefonu, linków i nagłówka z imieniem i nazwiskiem.

## Architektura

```
src/job_seeker/
  domain/models.py        modele niezależne od źródła (JobOffer, CandidateProfile, MatchResult…)
  sources/                integracje z serwisami: base.py (protokół JobSource) + registry.py
    justjoin/             klient API JustJoin.it + mapper JSON → JobOffer
  profile/                CV → profil: odczyt PDF, słownik umiejętności, wykrywanie zmian, poprawki
  matching/
    rules.py              filtry + scoring regułowy
    ai/                   wymienni dostawcy AI (anthropic, openai_compatible) ze wspólnym promptem
    pipeline.py           filtry → reguły → [AI] → ranking
  storage/db.py           SQLite: oferty, cache ocen AI, historia synchronizacji
  services/job_seeker.py  logika aplikacji współdzielona przez CLI i API
  cli.py, api/            interfejsy
```

### Nowy serwis z ofertami

1. Utwórz `sources/<nazwa>/` z klasą implementującą `JobSource` (`fetch_offers`, `fetch_details`, `list_categories`, `aclose`), która mapuje dane serwisu na `JobOffer`.
2. Zarejestruj ją w `sources/registry.py` (`register("<nazwa>", factory)`).
3. Dodaj nazwę do `search.sources` w `config.toml`.

Matching, cache, CLI i API zadziałają bez dalszych zmian.

### Inny model AI

- **Claude:** wystarczy zmienić `ai.model`.
- **Inni dostawcy** (OpenAI, OpenRouter, lokalna Ollama lub LM Studio): `uv sync --extra openai`, a w configu `provider = "openai_compatible"`, `model` i ewentualnie `base_url`.
- **Własny dostawca:** zaimplementuj `AIScorer` w `matching/ai/` i dodaj go do `matching/ai/registry.py`.

## Rozwój

```bash
uv sync --all-extras
uv run pytest
uv run ruff check . && uv run ruff format .
uv run mypy src tests
```
