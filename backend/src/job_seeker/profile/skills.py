"""Skill vocabulary: canonical names, aliases and relations used by both CV parsing and offer scoring.

Offer skills are free text ("Node", "NodeJS", "Node.js"), so everything is mapped to one canonical
name before comparison. Unknown skills are kept as their lowercased form.
"""

from __future__ import annotations

import re

from job_seeker.utils.text import fold

# canonical name -> aliases (matched case-insensitively as whole words; canonical name is implied)
SKILL_ALIASES: dict[str, tuple[str, ...]] = {
    "javascript": ("js", "ecmascript", "es6"),
    "typescript": ("ts",),
    "node.js": ("node", "nodejs", "node js"),
    "nestjs": ("nest.js", "nest"),
    "express": ("express.js", "expressjs"),
    "python": ("python3",),
    "django": (),
    "fastapi": (),
    "flask": (),
    "go": ("golang",),
    "java": (),
    "kotlin": (),
    "c#": ("csharp",),
    ".net": ("dotnet", ".net core", "asp.net"),
    "php": (),
    "ruby": (),
    "rust": (),
    "c++": ("cpp", "c/c++"),
    "scala": (),
    "terraform": (),
    "aws": ("amazon web services", "lambda", "aws lambda", "ec2", "s3"),
    "gcp": ("google cloud", "google cloud platform"),
    "azure": ("microsoft azure",),
    "docker": (),
    "kubernetes": ("k8s",),
    "linux": (),
    "postgresql": ("postgres", "psql"),
    "mysql": ("mariadb",),
    "mongodb": ("mongo",),
    "redis": (),
    "elasticsearch": ("elastic", "opensearch"),
    "sql": (),
    "nosql": (),
    "rabbitmq": ("rabbit",),
    "kafka": ("apache kafka",),
    "graphql": (),
    "rest": ("rest api", "restful", "restful api", "rest apis"),
    "grpc": (),
    "microservices": ("microservice", "micro-services", "microservice architecture"),
    "event-driven architecture": ("event-driven", "event driven", "eda"),
    "react": ("react.js", "reactjs"),
    "angular": ("angularjs",),
    "vue.js": ("vue", "vuejs"),
    "next.js": ("nextjs",),
    "html": ("html5",),
    "css": ("css3", "scss", "sass"),
    "jest": (),
    "testing": ("software testing", "unit testing", "automated tests", "tdd"),
    "ci/cd": ("cicd", "ci", "continuous integration", "github actions", "gitlab ci", "jenkins"),
    "git": (),
    "solid": (),
    "clean architecture": ("hexagonal architecture", "ddd", "domain-driven design"),
    "software architecture": ("system design", "architecture"),
    "concurrency": ("multithreading", "asynchronous programming"),
    "scrum": ("agile",),
    "llm": ("ai", "genai", "openai", "large language models"),
}

# Having the key implies basic knowledge of the listed skills (weight multiplied by IMPLIED_WEIGHT).
IMPLIES: dict[str, tuple[str, ...]] = {
    "typescript": ("javascript",),
    "node.js": ("javascript",),
    "nestjs": ("node.js", "typescript"),
    "express": ("node.js",),
    "postgresql": ("sql",),
    "mysql": ("sql",),
    "mongodb": ("nosql",),
    "rabbitmq": ("event-driven architecture",),
    "kafka": ("event-driven architecture",),
    "jest": ("testing",),
    "django": ("python",),
    "fastapi": ("python",),
    "next.js": ("react",),
}
IMPLIED_WEIGHT = 0.6

# Partial credit when the offer asks for X and the candidate knows a close sibling of X.
RELATED: dict[str, tuple[str, ...]] = {
    "sql": ("postgresql", "mysql"),
    "postgresql": ("mysql",),
    "mysql": ("postgresql",),
    "nosql": ("mongodb", "redis"),
    "kafka": ("rabbitmq",),
    "rabbitmq": ("kafka",),
    "gcp": ("aws", "azure"),
    "azure": ("aws", "gcp"),
    "aws": ("gcp", "azure"),
    "nestjs": ("express",),
    "express": ("nestjs",),
    "kubernetes": ("docker",),
    "event-driven architecture": ("rabbitmq", "kafka"),
    "microservices": ("event-driven architecture",),
}
RELATED_CREDIT = 0.5

_ALIAS_TO_CANONICAL: dict[str, str] = {}
for _canonical, _aliases in SKILL_ALIASES.items():
    _ALIAS_TO_CANONICAL[fold(_canonical)] = _canonical
    for _alias in _aliases:
        _ALIAS_TO_CANONICAL[fold(_alias)] = _canonical

# Aliases that are ordinary English words / too ambiguous to detect in free CV text.
_TEXT_DETECTION_SKIP = {
    "go",
    "js",
    "ts",
    "ci",
    "node",
    "nest",
    "rest",
    "elastic",
    "rabbit",
    "ai",
    "eda",
    "architecture",
    "solid",
}
_CASE_SENSITIVE_TEXT_PATTERNS: dict[str, tuple[str, ...]] = {
    "go": ("Go", "Golang"),
    "rest": ("REST",),
    "llm": ("LLM", "LLMs", "GenAI"),
    "solid": ("SOLID",),
}


def canonical_skill(name: str) -> str:
    """'NodeJS' -> 'node.js'; unknown skills are returned folded (lowercase, no diacritics)."""
    key = fold(name)
    if key in _ALIAS_TO_CANONICAL:
        return _ALIAS_TO_CANONICAL[key]
    stripped = re.sub(r"\s*\(.*?\)\s*", " ", key).strip()  # "Optimizely (Episerver)" -> "optimizely"
    return _ALIAS_TO_CANONICAL.get(stripped, stripped or key)


def find_skills_in_text(text: str) -> dict[str, int]:
    """Count mentions of known skills in free text (e.g. a CV). Returns canonical name -> mentions."""
    counts: dict[str, int] = {}
    folded = fold(text)
    for match in _TEXT_PATTERN.finditer(folded):
        canonical = _ALIAS_TO_CANONICAL[match.group(0)]
        counts[canonical] = counts.get(canonical, 0) + 1
    for canonical, patterns in _CASE_SENSITIVE_TEXT_PATTERNS.items():
        for pattern in patterns:
            mentions = len(re.findall(rf"(?<![\w.#+]){re.escape(pattern)}(?![\w#+])", text))
            if mentions:
                counts[canonical] = counts.get(canonical, 0) + mentions
    return counts


def _build_text_pattern() -> re.Pattern[str]:
    terms = {fold(t) for c, aliases in SKILL_ALIASES.items() for t in (c, *aliases) if t not in _TEXT_DETECTION_SKIP}
    # Longest first so "express.js" wins over "express" and each mention is counted once.
    alternation = "|".join(re.escape(t) for t in sorted(terms, key=len, reverse=True))
    return re.compile(rf"(?<![\w.#+])(?:{alternation})(?![\w#+])")


_TEXT_PATTERN = _build_text_pattern()
