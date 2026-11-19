Create a new FastAPI route module for the feature described below.

Arguments: $ARGUMENTS

## Instructions

1. Create `src/routes/<name>.py` with:
   - An `APIRouter` with an appropriate `prefix` and `tags`
   - At least one endpoint that demonstrates the pattern (GET list, POST create, etc.)
   - Use `request.state.ctx` to access `RequestContext`
   - Import `get_auth_context` from `auth.dependency` and protect endpoints that need auth using `Depends(get_auth_context)`  # noqa: B008
   - Return typed Pydantic response models (define them at the top of the file)

2. Register the router in `src/app.py`:
   - Import the new module in the routes section
   - Add `app.include_router(<name>.router)` alongside the existing health/metrics routers

3. Add at least one pytest test in `tests/test_<name>.py` using the `client` fixture from `conftest.py`.

4. Run `uv run ruff check --fix src/ tests/`, `uv run ruff format src/ tests/` and `uv run mypy src/` after creating the files.

## Conventions

- Line length: 100
- No `from __future__ import annotations` — Python 3.14+ evaluates annotations lazily (PEP 649)
- Fully type-annotated — `mypy` runs in strict mode and must stay clean
- No bare `except:` — always catch a specific exception type
