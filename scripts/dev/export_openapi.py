"""Export the backend's OpenAPI schema to a static JSON file for codegen.

Drives the chess-coach FastAPI app via `create_app()` and writes the resulting
OpenAPI 3.1 schema to `.openapi.json` at the repo root. Used as the input
for the `openapi-typescript` codegen step that produces
`apps/desktop/src/services/coach/api.ts`.

Per FU-4 BBF investigation (2026-08-04): `create_app() + app.openapi()` is
self-contained — no filesystem writes, no subprocess spawns, no DB migrations
beyond what `_configure_logging()` does on import (root logger handler reset).
The lifespan handler (`_lifespan`) does NOT fire here because nothing wraps
the app in a context manager; `app.openapi()` is a pure route-introspection
method.

Usage:
    python scripts/dev/export_openapi.py
    python scripts/dev/export_openapi.py --output .openapi.json

The default output path is `<repo-root>/.openapi.json`. The file is gitignored
because it's a regenerated artifact (per FU-4 BBF design: regen produces a
file that gets diffed in the CI check, not a file that gets committed).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export backend OpenAPI schema to a static JSON file."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[2] / ".openapi.json",
        help="Output path for the schema JSON file (default: <repo-root>/.openapi.json).",
    )
    args = parser.parse_args()

    # Late import so `--help` doesn't trigger the chess_coach import chain.
    from chess_coach.gateway.app import create_app  # noqa: E402

    app = create_app()
    schema = app.openapi()

    args.output.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
    paths = len(schema.get("paths", {}))
    schemas = len(schema.get("components", {}).get("schemas", {}))
    print(f"OK: wrote OpenAPI {schema.get('openapi')} schema to {args.output}")
    print(f"  paths: {paths}, components/schemas: {schemas}")
    return 0


if __name__ == "__main__":
    sys.exit(main())