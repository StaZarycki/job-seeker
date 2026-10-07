"""Write the API's OpenAPI schema, e.g. for generating the web frontend's TypeScript types.

Usage: ``uv run python -m job_seeker.api.export_openapi ../web/openapi.json``
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from job_seeker.api.app import create_app
from job_seeker.config import AppConfig


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        # A throwaway base dir: building the app must not touch the real database or CV folder.
        schema = create_app(AppConfig(base_dir=Path(tmp))).openapi()
    text = json.dumps(schema, ensure_ascii=False, indent=2) + "\n"
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
