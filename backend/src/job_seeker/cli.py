"""Command line interface: ``uv run jobseeker --help``."""

from __future__ import annotations

import asyncio
import io
import logging
import sys
from pathlib import Path
from typing import Annotated, NoReturn

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from job_seeker.config import MatchingMode, load_config
from job_seeker.domain.models import MatchResult
from job_seeker.matching.ai.base import AIConfigurationError
from job_seeker.matching.pipeline import MatchReport
from job_seeker.profile.service import CVNotFoundError, ProfileState
from job_seeker.services.job_seeker import JobSeekerService, MatchRequest, SyncResult
from job_seeker.sources.base import SourceError
from job_seeker.sources.registry import available_sources

for _stream in (sys.stdout, sys.stderr):
    # Windows consoles/pipes may default to cp1252, which can't print Polish characters.
    if isinstance(_stream, io.TextIOWrapper) and (_stream.encoding or "").lower() not in ("utf-8", "utf8"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

app = typer.Typer(help="Znajduje oferty pracy najlepiej pasujące do Twojego CV.", no_args_is_help=True)
profile_app = typer.Typer(help="Profil kandydata zbudowany z CV.", no_args_is_help=True)
app.add_typer(profile_app, name="profile")
console = Console()

ConfigOption = Annotated[Path | None, typer.Option("--config", help="Ścieżka do config.toml")]


SearchOption = Annotated[
    str | None, typer.Option("--search", help="Profil wyszukiwania z [searches.<nazwa>] w config.toml")
]


def _service(config_path: Path | None) -> JobSeekerService:
    try:
        return JobSeekerService(load_config(config_path))
    except ValueError as exc:  # includes pydantic ValidationError for a broken config.toml
        _fail(f"Błędna konfiguracja: {exc}")


@app.callback()
def main(verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Więcej logów")] = False) -> None:
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING, format="%(levelname)s %(name)s: %(message)s"
    )


@profile_app.command("show")
def profile_show(config: ConfigOption = None) -> None:
    """Pokaż profil (przebudowuje go automatycznie, jeśli CV się zmieniło)."""
    state = _load_profile(_service(config))
    _print_profile(state)


@profile_app.command("build")
def profile_build(config: ConfigOption = None) -> None:
    """Wymuś ponowne zbudowanie profilu z CV."""
    state = _load_profile(_service(config), force=True)
    _print_profile(state)


@app.command()
def sync(
    source: Annotated[list[str] | None, typer.Option("--source", "-s", help="Źródło (domyślnie z configu)")] = None,
    category: Annotated[list[str] | None, typer.Option("--category", "-c", help="Kategoria, np. javascript")] = None,
    limit: Annotated[int | None, typer.Option(help="Maksymalna liczba ofert na źródło (do testów)")] = None,
    search: SearchOption = None,
    config: ConfigOption = None,
) -> None:
    """Pobierz aktualne oferty do lokalnej bazy."""
    service = _service(config)
    try:
        prefs = service.preferences(search)
    except ValueError as exc:
        _fail(str(exc))
    categories = category or prefs.categories
    console.print(f"Pobieram oferty: źródła {', '.join(source or prefs.sources)}; "
                  f"kategorie {', '.join(categories) or 'wszystkie'}...")  # fmt: skip

    def done(result: SyncResult) -> None:
        if result.error:
            console.print(f"[red]✗ {result.source}: {escape(result.error)}[/] (zapisano {result.fetched} ofert)")
        else:
            console.print(f"[green]✓ {result.source}[/]: {result.fetched} ofert, w tym {result.new} nowych")

    try:
        results = asyncio.run(service.sync(source, category, limit, on_source_done=done, search=search))
    except ValueError as exc:
        _fail(str(exc))
    if any(r.error for r in results):
        raise typer.Exit(1)


@app.command()
def match(
    top: Annotated[int, typer.Option("--top", "-n", help="Ile ofert pokazać")] = 20,
    mode: Annotated[MatchingMode | None, typer.Option(help="basic = tylko reguły, ai = reguły + model AI")] = None,
    provider: Annotated[str | None, typer.Option(help="Dostawca AI: anthropic | openai_compatible")] = None,
    model: Annotated[str | None, typer.Option(help="Model AI, np. claude-haiku-4-5")] = None,
    category: Annotated[list[str] | None, typer.Option("--category", "-c", help="Zawęź do kategorii")] = None,
    min_score: Annotated[float | None, typer.Option(help="Pokaż tylko oferty z wynikiem >= tej wartości")] = None,
    details: Annotated[bool, typer.Option("--details", "-d", help="Pokaż uzasadnienie dla każdej oferty")] = False,
    search: SearchOption = None,
    config: ConfigOption = None,
) -> None:
    """Pokaż oferty najlepiej pasujące do Twojego profilu."""
    service = _service(config)
    request = MatchRequest(
        mode=mode, top=top, provider=provider, model=model, min_score=min_score, search=search,
        preferences={"categories": category} if category else {},
    )  # fmt: skip

    def on_ai_plan(to_call: int, cached: int) -> None:
        used = f"{provider or service.config.ai.provider}, {model or service.config.ai.model}"
        console.print(f"Ocena AI ({used}): {to_call} zapytań do modelu, {cached} z cache.")

    try:
        outcome = asyncio.run(service.match(request, on_ai_plan=on_ai_plan))
    except (CVNotFoundError, AIConfigurationError, ValueError) as exc:
        _fail(str(exc))
    _print_profile_notice(outcome.profile)
    _print_report(outcome.report, details)


@app.command()
def categories(
    source: Annotated[str, typer.Option("--source", "-s")] = "justjoin",
    config: ConfigOption = None,
) -> None:
    """Lista kategorii dostępnych w źródle (do użycia w search.categories)."""
    try:
        items = asyncio.run(_service(config).list_categories(source))
    except (SourceError, ValueError) as exc:
        _fail(str(exc))
    table = Table("kategoria", "ofert")
    for item in items:
        table.add_row(item.key, str(item.count or "-"))
    console.print(table)


@app.command()
def offer(offer_id: str, config: ConfigOption = None) -> None:
    """Pokaż szczegóły oferty, np. `jobseeker offer justjoin:<id>`."""
    try:
        found = asyncio.run(_service(config).offer_with_details(offer_id))
    except SourceError as exc:
        _fail(str(exc))
    if found is None:
        _fail(f"Nie ma oferty {offer_id} w bazie.")
    console.print(f"[bold]{escape(found.title)}[/] @ {escape(found.company)}\n{found.url}\n")
    console.print(escape(found.description or "(brak opisu)"))


@app.command()
def searches(config: ConfigOption = None) -> None:
    """Lista profili wyszukiwania ([searches.<nazwa>] w config.toml)."""
    service = _service(config)
    if not service.config.searches:
        console.print("Brak profili. Dodaj np. [searches.cpp] w config.toml (wzór w config.example.toml).")
        return
    for name, overrides in sorted(service.config.searches.items()):
        settings = "; ".join(f"{key} = {value}" for key, value in overrides.items())
        console.print(f"[bold]{name}[/]: {escape(settings)}")


@app.command()
def sources() -> None:
    """Lista obsługiwanych serwisów z ofertami."""
    for name in available_sources():
        console.print(name)


@app.command()
def serve(
    host: str = "127.0.0.1",
    port: int = 8000,
    reload: Annotated[bool, typer.Option(help="Automatyczny restart po zmianach w kodzie")] = False,
) -> None:
    """Uruchom REST API (dokumentacja: http://127.0.0.1:8000/docs)."""
    import uvicorn

    uvicorn.run("job_seeker.api.app:create_app", factory=True, host=host, port=port, reload=reload)


# --- output helpers -----------------------------------------------------------------------------------


def _load_profile(service: JobSeekerService, force: bool = False) -> ProfileState:
    try:
        state = service.load_profile(force_rebuild=force)
    except (CVNotFoundError, ValueError) as exc:
        _fail(str(exc))
    _print_profile_notice(state)
    return state


def _print_profile_notice(state: ProfileState) -> None:
    if state.rebuilt:
        reason = "nowe/zmienione CV lub aktualizacja aplikacji"
        console.print(f"[cyan]Profil przebudowany z {state.profile.source_file} ({reason}).[/]")
    if state.warning:
        console.print(f"[yellow]{escape(state.warning)}[/]")


def _print_profile(state: ProfileState) -> None:
    p = state.profile
    console.print(f"[bold]{escape(p.headline or 'Profil')}[/]  ({escape(p.location or '-')})")
    console.print(f"CV: {p.source_file}   hash profilu: {state.profile_hash}")
    console.print(f"Doświadczenie: {p.years_of_experience:g} lat → poziom [bold]{p.seniority.value}[/]")
    console.print("Języki: " + ", ".join(f"{k} {v}" for k, v in p.languages.items()))
    core = [s.name for s in p.skills if s.weight >= 1]
    other = [f"{s.name} ({s.weight:.2f})" for s in p.skills if s.weight < 1]
    console.print(f"Główne umiejętności: [green]{escape(', '.join(core))}[/]")
    console.print(f"Pozostałe: {escape(', '.join(other))}")
    years = ", ".join(f"{name} {value:g}" for name, value in sorted(p.skill_years.items(), key=lambda kv: -kv[1]))
    console.print(f"Lata w pozycjach z CV: {escape(years or '-')}")
    console.print("[dim]Poprawki wpisz w profile.overrides.toml - przetrwają zmianę CV.[/]")


def _print_report(report: MatchReport, details: bool) -> None:
    console.print(
        f"Przeanalizowano {report.considered} ofert, {report.filtered_out} odrzucono filtrami "
        f"(tryb: [bold]{report.mode.value}[/])."
    )
    if report.mode is MatchingMode.AI:
        console.print(
            f"AI: {report.ai_calls} nowych ocen, {report.ai_cached} z cache, {report.ai_failed} błędów; "
            f"tokeny: {report.input_tokens} wej. / {report.output_tokens} wyj."
        )
        for error in report.errors[:5]:
            console.print(f"[yellow]  ! {escape(error)}[/]")
    if not report.results:
        console.print(
            "[yellow]Brak ofert. Uruchom najpierw `jobseeker sync` albo poluzuj preferencje w config.toml.[/]"
        )
        return

    table = Table(show_lines=True)
    table.add_column("#", justify="right")
    table.add_column("Wynik", justify="right")
    table.add_column("Oferta")
    table.add_column("Poziom / tryb")
    table.add_column("Widełki (PLN/mies.)")
    table.add_column("Umiejętności")
    for i, r in enumerate(report.results, 1):
        table.add_row(str(i), _score_cell(r), _offer_cell(r), _level_cell(r), _salary_cell(r), _skills_cell(r))
    console.print(table)

    if details:
        for i, r in enumerate(report.results, 1):
            _print_details(i, r)


def _score_cell(r: MatchResult) -> str:
    if r.ai is None:
        return f"[bold]{r.final_score:.0f}[/]"
    return f"[bold]{r.final_score:.0f}[/]\n[dim]AI {r.ai.assessment.score}\nreg. {r.rule.score:.0f}[/]"


def _offer_cell(r: MatchResult) -> str:
    o = r.offer
    return f"[bold][link={o.url}]{escape(o.title)}[/link][/]\n{escape(o.company)}\n[dim]{o.url}[/]"


def _level_cell(r: MatchResult) -> str:
    o = r.offer
    cities = ", ".join(dict.fromkeys(loc.city for loc in o.locations))
    level = o.seniority.value if o.seniority else "?"
    workplace = o.workplace_type.value if o.workplace_type else "?"
    yours = f"\n[dim]Ty: ~{r.rule.effective_years:g} l.[/]" if r.rule.effective_years is not None else ""
    return f"{level}{yours}\n{workplace}\n[dim]{escape(cities)}[/]"


def _salary_cell(r: MatchResult) -> str:
    s = r.offer.best_salary
    if s is None:
        return "[dim]brak[/]"
    low = f"{s.min_pln_month:,.0f}".replace(",", " ") if s.min_pln_month else "?"
    high = f"{s.max_pln_month:,.0f}".replace(",", " ") if s.max_pln_month else "?"
    return f"{low} - {high}\n[dim]{s.contract}{', brutto' if s.gross else ''}[/]"


def _skills_cell(r: MatchResult) -> str:
    matched = ", ".join(r.rule.matched_skills) or "-"
    missing = ", ".join(r.ai.assessment.missing_skills if r.ai else r.rule.missing_skills) or "-"
    return f"[green]✓ {escape(matched)}[/]\n[red]✗ {escape(missing)}[/]"


def _print_details(i: int, r: MatchResult) -> None:
    console.rule(f"#{i} {escape(r.offer.title)} @ {escape(r.offer.company)}")
    console.print(f"{r.offer.url}   [dim]id: {r.offer.id}[/]")
    breakdown = ", ".join(f"{k} {v:.2f}" for k, v in r.rule.breakdown.items())
    console.print(f"[dim]Reguły {r.rule.score:.0f}: {breakdown}[/]")
    console.print("[dim]" + escape(" · ".join(r.rule.notes)) + "[/]")
    if r.ai:
        a = r.ai.assessment
        console.print(f"[bold]AI ({r.ai.model}) {a.score}/100:[/] {escape(a.summary)}")
        for pro in a.pros:
            console.print(f"  [green]+[/] {escape(pro)}")
        for con in a.cons:
            console.print(f"  [red]-[/] {escape(con)}")


def _fail(message: str) -> NoReturn:
    console.print(f"[red]{escape(message)}[/]")
    raise typer.Exit(1)


if __name__ == "__main__":
    app()
