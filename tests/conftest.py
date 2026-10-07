from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from job_seeker.config import AppConfig, PathsConfig
from job_seeker.domain.models import CandidateProfile, CandidateSkill, JobOffer, Seniority
from job_seeker.sources.justjoin.mapper import map_offer

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def offers_page() -> dict[str, Any]:
    page: dict[str, Any] = load_fixture("justjoin_offers.json")
    return page


@pytest.fixture
def offer_detail() -> dict[str, Any]:
    detail: dict[str, Any] = load_fixture("justjoin_offer_detail.json")
    return detail


@pytest.fixture
def offers(offers_page: dict[str, Any]) -> list[JobOffer]:
    return [map_offer(raw) for raw in offers_page["data"]]


@pytest.fixture
def profile() -> CandidateProfile:
    """Backend Node/TS developer similar to the real CV."""
    core = ["node.js", "typescript", "javascript", "python", "aws", "rabbitmq", "postgresql", "mongodb", "rest"]
    secondary = ["docker", "nestjs", "express", "go", "terraform", "jest", "microservices"]
    return CandidateProfile(
        source_file="cv.pdf",
        source_hash="abc",
        built_at=datetime(2026, 10, 1, tzinfo=UTC),
        headline="Software Developer",
        location="Katowice, Poland",
        years_of_experience=4,
        seniority=Seniority.MID,
        skills=[CandidateSkill(name=s, weight=1.0) for s in core]
        + [CandidateSkill(name=s, weight=0.75) for s in secondary]
        + [CandidateSkill(name="sql", weight=0.6)],
        languages={"pl": "C2", "en": "C1"},
        cv_text="About me\nBackend developer, Node.js, TypeScript.",
    )


@pytest.fixture
def app_config(tmp_path: Path) -> AppConfig:
    return AppConfig(
        base_dir=tmp_path,
        paths=PathsConfig(cv_dir=Path("cv"), data_dir=Path("data"), overrides=Path("profile.overrides.toml")),
    )


def make_pdf(text_lines: list[str]) -> bytes:
    """Build a minimal valid single-page PDF containing ``text_lines`` (Helvetica, ASCII only)."""
    content_ops = ["BT", "/F1 11 Tf", "14 TL", "50 790 Td"]
    for line in text_lines:
        escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        content_ops.append(f"({escaped}) Tj T*")
    content_ops.append("ET")
    stream = "\n".join(content_ops).encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{off:010d} 00000 n \n".encode() for off in offsets)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


SAMPLE_CV = [
    "Jan Kowalski",
    "Backend Developer",
    "Katowice, Poland",
    "jan@example.com | +48 600 700 800",
    "About me",
    "Backend developer with 3+ years of experience in Node.js and TypeScript.",
    "Experience",
    "Backend Developer, ACME 2022 - Present",
    "Built REST APIs with Node.js, PostgreSQL and Docker.",
    "Skills",
    "TypeScript, Node.js, PostgreSQL, Docker, Kafka",
    "Spoken Languages Polish - Native, English - B2",
    "I agree to the processing of personal data provided in this document.",
]
