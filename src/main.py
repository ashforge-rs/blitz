from __future__ import annotations

# ---------------------------------------------------------------------------
# Root entry point — delegates to src/services/api/main.py.
#
# This file exists for backward compatibility with Uvicorn invocations that
# use `main:app`.  The canonical entry point for the default API service is:
#
#   uvicorn services.api.main:app
#
# Additional services live under src/services/<name>/main.py and are started
# independently on different ports.
# ---------------------------------------------------------------------------
from services.api.main import app, main

__all__ = ["app", "main"]


if __name__ == "__main__":
    main()
