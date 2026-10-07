"""Extract text and structured facts from a CV PDF."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from pypdf import PdfReader

from job_seeker.domain.models import Seniority
from job_seeker.utils.text import fold

_SECTION_HEADINGS = (
    "about me", "summary", "profile", "o mnie", "podsumowanie",
    "experience", "work experience", "professional experience", "doswiadczenie", "doswiadczenie zawodowe",
    "skills", "umiejetnosci", "technical skills",
    "education", "wyksztalcenie",
    "projects", "projekty",
    "languages", "jezyki",
)  # fmt: skip
_EXPERIENCE_HEADINGS = {
    "experience",
    "work experience",
    "professional experience",
    "doswiadczenie",
    "doswiadczenie zawodowe",
}
_PRESENT_WORDS = r"present|now|current|currently|today|obecnie|teraz|nadal"
_YEAR_RANGE = re.compile(
    rf"(?P<start>(?:19|20)\d{{2}})\s*[-–—]\s*(?P<end>(?:19|20)\d{{2}}|{_PRESENT_WORDS})", re.IGNORECASE
)
_STATED_YEARS = re.compile(
    r"(?P<years>\d+(?:[.,]\d)?)\s*\+?\s*(?:years?|yrs?|lat|lata)\s+(?:of\s+)?(?:commercial\s+|professional\s+)?"
    r"(?:experience|doswiadczenia)",
    re.IGNORECASE,
)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"(?:\(?\+?\d{2,3}\)?[\s-]?)?(?:\d{3}[\s-]?){2}\d{3}")
_URL = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
_CONSENT = re.compile(r"(I agree to the processing|Wyrażam zgodę na przetwarzanie).*", re.IGNORECASE | re.DOTALL)

LANGUAGE_CODES = {
    "polish": "pl", "polski": "pl", "english": "en", "angielski": "en", "german": "de", "niemiecki": "de",
    "french": "fr", "francuski": "fr", "spanish": "es", "hiszpanski": "es", "italian": "it", "wloski": "it",
    "japanese": "ja", "japonski": "ja", "russian": "ru", "rosyjski": "ru", "ukrainian": "uk", "ukrainski": "uk",
    "portuguese": "pt", "portugalski": "pt", "dutch": "nl", "czech": "cs", "chinese": "zh", "norwegian": "no",
}  # fmt: skip
_LEVEL_WORDS = {"native": "C2", "ojczysty": "C2", "fluent": "C1", "biegly": "C1", "advanced": "C1",
                "intermediate": "B1", "basic": "A2", "podstawowy": "A2"}  # fmt: skip


class CVReadError(RuntimeError):
    pass


def extract_text(path: Path) -> str:
    try:
        reader = PdfReader(path)
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as exc:  # pypdf raises a variety of errors for broken files
        raise CVReadError(f"Cannot read CV '{path.name}': {exc}") from exc
    if not text.strip():
        raise CVReadError(f"CV '{path.name}' contains no extractable text (scanned PDF?)")
    return text


def split_sections(text: str) -> dict[str, str]:
    """Split CV text by well-known headings. Text before the first heading is stored under 'header'."""
    sections: dict[str, list[str]] = {"header": []}
    current = "header"
    for line in text.splitlines():
        key = fold(line).strip(" :")
        if key in _SECTION_HEADINGS:
            current = key
            sections.setdefault(current, [])
            continue
        sections[current].append(line)
    return {name: "\n".join(lines).strip() for name, lines in sections.items()}


def sanitize(text: str) -> str:
    """Remove the header block (name, contacts), contact data and the GDPR consent clause."""
    sections = split_sections(text)
    if len(sections) > 1:
        lines = text.splitlines()
        first_heading = next(i for i, line in enumerate(lines) if fold(line).strip(" :") in _SECTION_HEADINGS)
        text = "\n".join(lines[first_heading:])
    text = _CONSENT.sub("", text)
    text = _EMAIL.sub("[email]", text)
    text = _URL.sub("[link]", text)
    text = _PHONE.sub("[phone]", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def headline_and_location(text: str) -> tuple[str | None, str | None]:
    header = split_sections(text).get("header", "")
    lines = [line.strip() for line in header.splitlines() if line.strip()]
    location = next((m.group(0) for line in lines if (m := re.search(r"[\w\s-]+,\s*(Poland|Polska)", line))), None)
    headline = lines[1] if len(lines) > 1 and not _EMAIL.search(lines[1]) else None
    return headline, location.strip() if location else None


@dataclass(frozen=True)
class ExperienceEntry:
    """One position from the Experience section: years as decimals (2022.0 .. 2025.0) and its text."""

    start: float
    end: float
    text: str

    @property
    def years(self) -> float:
        return self.end - self.start


def years_of_experience(text: str, today: date | None = None) -> float:
    """Prefer an explicit 'N+ years of experience' statement, else sum (merged) date ranges in Experience."""
    stated = [float(m.group("years").replace(",", ".")) for m in _STATED_YEARS.finditer(text)]
    if stated:
        return max(stated)
    entries = experience_entries(text, today)
    if entries:
        return merged_years([(e.start, e.end) for e in entries])
    now = _decimal_year(today or date.today())
    return merged_years([_range(m, now) for m in _YEAR_RANGE.finditer(text)])


def experience_entries(text: str, today: date | None = None) -> list[ExperienceEntry]:
    """Split the Experience section into positions.

    Every line with a year range ('2022 - 2025', '2026 - Present') starts a position; the line just above
    it (job title) belongs to it too, as do all lines up to the next position's title.
    """
    sections = split_sections(text)
    body = "\n".join(content for name, content in sections.items() if name in _EXPERIENCE_HEADINGS)
    lines = body.splitlines()
    date_lines = [i for i, line in enumerate(lines) if _YEAR_RANGE.search(line)]
    starts = [i - 1 if i > 0 and (k == 0 or i - 1 > date_lines[k - 1]) else i for k, i in enumerate(date_lines)]
    now = _decimal_year(today or date.today())
    entries = []
    for k, i in enumerate(date_lines):
        match = _YEAR_RANGE.search(lines[i])
        assert match is not None
        start, end = _range(match, now)
        stop = starts[k + 1] if k + 1 < len(starts) else len(lines)
        entries.append(ExperienceEntry(start=start, end=end, text="\n".join(lines[starts[k] : stop])))
    return entries


def merged_years(intervals: list[tuple[float, float]]) -> float:
    """Total length of the union of ``intervals`` (overlapping jobs are not counted twice)."""
    total, cur_start, cur_end = 0.0, None, None
    for start, end in sorted(intervals):
        if cur_end is None or start > cur_end:
            if cur_start is not None and cur_end is not None:
                total += cur_end - cur_start
            cur_start, cur_end = start, end
        else:
            cur_end = max(cur_end, end)
    if cur_start is not None and cur_end is not None:
        total += cur_end - cur_start
    return round(total, 1)


def _range(match: re.Match[str], now: float) -> tuple[float, float]:
    start = float(match.group("start"))
    end_raw = match.group("end")
    end = float(end_raw) if end_raw[0].isdigit() else now
    return start, max(end, start + 0.5)  # "2020 - 2020" still means some months of work


def _decimal_year(day: date) -> float:
    return day.year + (day.month - 1) / 12


def seniority_for_years(years: float) -> Seniority:
    if years < 2:
        return Seniority.JUNIOR
    if years < 5:
        return Seniority.MID
    return Seniority.SENIOR


def spoken_languages(text: str) -> dict[str, str]:
    """Find 'English - C1' / 'Polish - Native' style entries. Returns ISO code -> CEFR level."""
    found: dict[str, str] = {}
    sections = split_sections(text)
    scope = [sections.get("languages", ""), sections.get("jezyki", "")]
    scope += [line for line in text.splitlines() if re.search(r"language|jezyk", fold(line))]
    folded = fold("\n".join(scope)) if any(s.strip() for s in scope) else fold(text)
    for name, code in LANGUAGE_CODES.items():
        m = re.search(rf"\b{name}\b\s*[-–:(]?\s*(?P<level>[abc][12]|n[1-5]|\w+)?", folded)
        if not m:
            continue
        level_raw = (m.group("level") or "").lower()
        if re.fullmatch(r"[abc][12]", level_raw):
            level = level_raw.upper()
        elif re.fullmatch(r"n[1-5]", level_raw):  # JLPT: N5 (basic) .. N1 (advanced)
            level = {"5": "A1", "4": "A2", "3": "B1", "2": "B2", "1": "C1"}[level_raw[1]]
        else:
            level = _LEVEL_WORDS.get(level_raw, "B1")
        found.setdefault(code, level)
    return found
