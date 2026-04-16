#!/usr/bin/env python
"""
Generate a static openapi.json from the running application schema.

Usage:
    uv run python scripts/generate_openapi.py
    uv run python scripts/generate_openapi.py --out docs/openapi.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure src/ is on the path when run from the project root.
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from app import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="Export OpenAPI schema to JSON.")
    parser.add_argument(
        "--out",
        default="openapi.json",
        help="Output file path (default: openapi.json)",
    )
    args = parser.parse_args()

    app = create_app()
    schema = app.openapi()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
    print(f"OpenAPI schema written to {out}  ({len(schema.get('paths', {}))} paths)")


if __name__ == "__main__":
    main()
