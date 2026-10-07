"""Small text helpers shared by sources, profile parsing and matching."""

from __future__ import annotations

import re
import unicodedata

from bs4 import BeautifulSoup

_BLOCK_TAGS = ("p", "li", "br", "div", "h1", "h2", "h3", "h4", "h5", "h6", "tr")
_CITY_ALIASES = {
    "cracow": "krakow",
    "warsaw": "warszawa",
    "wroclaw": "wroclaw",
    "breslau": "wroclaw",
    "posen": "poznan",
    "kattowitz": "katowice",
    "danzig": "gdansk",
}


def html_to_text(html: str) -> str:
    """Convert offer HTML into readable plain text, keeping paragraph and list structure."""
    soup = BeautifulSoup(html, "html.parser")
    for li in soup.find_all("li"):
        li.insert_before("\n- ")
    for tag in soup.find_all(_BLOCK_TAGS):
        tag.insert_after("\n")
    text = soup.get_text()
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def fold(value: str) -> str:
    """Lowercase and strip diacritics: 'Kraków' -> 'krakow' (note: 'ł' is handled explicitly)."""
    value = value.replace("ł", "l").replace("Ł", "L")
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(c for c in normalized if not unicodedata.combining(c)).lower().strip()


def normalize_city(city: str) -> str:
    folded = fold(city)
    return _CITY_ALIASES.get(folded, folded)


def contains_word(text: str, word: str) -> bool:
    """Case-insensitive whole-word match that also works for words like 'C#' or '.NET'."""
    pattern = rf"(?<![\w.#+]){re.escape(word.lower())}(?![\w#+])"
    return re.search(pattern, text.lower()) is not None
