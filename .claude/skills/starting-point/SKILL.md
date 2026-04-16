---
name: starting-point
description: >
  Interactive setup guide for new blitz projects. Collects project name,
  environment settings, auth, CORS, rate limiting, observability, and
  OpenTofu/GitHub config, then applies every change in one pass. Use when
  a user has just cloned the template and wants to configure it for their
  project.
license: MIT
metadata:
  author: blitz
  version: "1.0"
---

Walk the user through every configuration decision needed to turn this
template into their project. Collect all answers first, then apply all
changes in a single pass at the end — never make partial edits mid-interview.

---

## Step 1 — Collect answers

Ask the following questions. Group them into one prompt so the user answers
everything at once rather than one at a time. Use the `vscode_askQuestions`
tool with the questions array below.

### Questions to ask

**1. project_name**
> What is the name of your project? (kebab-case, e.g. `my-api`)
> This becomes the package name, `OPENAPI_TITLE`, `OTEL_SERVICE_NAME`, and
> the Terraform repository name.

**2. project_description**
> One-sentence description of what this API does.
> Used in `pyproject.toml`, `OPENAPI_DESCRIPTION`, and `infra/repository.tf`.

**3. github_owner**
> GitHub username or organisation that owns the repository.
> Used in `infra/variables.tf` and `CODEOWNERS`.

**4. python_version**
> Minimum Python version to support.
> Options: `3.11`, `3.12`, `3.13`. Default: `3.12`.

**5. environment**
> Target deployment environment for your `.env`.
> Options: `development`, `production`. Default: `development`.

**6. cors_origins**
> Allowed CORS origins (comma-separated). Use `*` for unrestricted (dev only).
> If you enter specific origins, `CORS_ALLOW_CREDENTIALS` will be set to `true`.

**7. rate_limit**
> Rate limit per IP. Format: `N/period` (e.g. `100/minute`, `1000/hour`).
> Default: `100/minute`.

**8. auth_required**
> Will this API require authentication on protected routes?
> Options: `yes`, `no`. Default: `no`.
> Choosing `yes` generates an `AuthProvider` stub in `src/auth/provider.py`.

**9. otel_enabled**
> Enable OpenTelemetry tracing?
> Options: `yes`, `no`. Default: `no`.
> If yes, ask for the OTLP collector endpoint (e.g. `http://localhost:4318/v1/traces`).

**10. metrics_auth**
> Should `/metrics` require authentication?
> Options: `yes`, `no`. Default: `no`.

**11. delete_example**
> Delete the `src/domains/example/` domain and its tests?
> Options: `yes`, `no`. Default: `yes`.

---

## Step 2 — Confirm before writing

Present a summary table of all collected values and ask:
> "Ready to apply these settings? I will update pyproject.toml, .env,
> infra/variables.tf, infra/repository.tf, CODEOWNERS, and optionally
> generate an AuthProvider stub and remove the example domain."

Wait for explicit confirmation before proceeding.

---

## Step 3 — Apply changes

Apply **all** changes below. Use `multi_replace_string_in_file` for batched
edits within and across files. Never leave the project in a half-configured
state.

### 3a — pyproject.toml

- `name` → `{project_name}`
- `description` → `{project_description}`
- `requires-python` → `>={python_version}`
- `[tool.ruff] target-version` → `py{python_version_nodot}`
  (e.g. `3.12` → `py312`)
- `[tool.mypy] python_version` → `"{python_version}"`

### 3b — .env

Copy `.env.example` to `.env` (only if `.env` does not already exist — never
overwrite an existing `.env`).

Apply the following substitutions:

| Variable | Value |
|---|---|
| `OPENAPI_TITLE` | `{project_name}` |
| `OPENAPI_DESCRIPTION` | `{project_description}` |
| `ENVIRONMENT` | `{environment}` |
| `ALLOWED_ORIGINS` | `{cors_origins}` |
| `CORS_ALLOW_CREDENTIALS` | `true` if origins are explicit, else `false` |
| `RATE_LIMIT` | `{rate_limit}` |
| `METRICS_REQUIRE_AUTH` | `true` if `{metrics_auth}` is `yes` |
| `OTEL_ENABLED` | `true` if `{otel_enabled}` is `yes` |
| `OTEL_SERVICE_NAME` | `{project_name}` |
| `OTEL_ENDPOINT` | `{otel_endpoint}` if provided |

### 3c — infra/variables.tf

- `default` of `github_owner` → `"{github_owner}"`
- `default` of `repository_name` → `"{project_name}"`

### 3d — infra/repository.tf

- `name` → `{project_name}`
- `description` → `{project_description}`

### 3e — infra/terraform.tfvars.example

- `github_owner` → `"{github_owner}"`
- `repository_name` → `"{project_name}"`

### 3f — .github/CODEOWNERS

Replace every occurrence of the placeholder owner (`@ashforge-rs`) with
`@{github_owner}`.

### 3g — .github/workflows/ci.yml and release-please.yml

If `{python_version}` differs from the current `PYTHON_PRIMARY`:
- Update `PYTHON_PRIMARY` in both workflow `env:` blocks.
- Update the matrix literal `["3.12", "3.13"]` — use `["{python_version}", ...]`
  keeping the latest stable version as the second entry.
- Update the coverage upload `if:` guard to the new primary version.

### 3h — AuthProvider stub (only if `auth_required` is `yes`)

Create `src/auth/provider.py` with the following content:

```python
from __future__ import annotations

from starlette.requests import Request

from context import RequestContext


class {ProjectNamePascal}AuthProvider:
    """
    Stub AuthProvider for {project_name}.

    Implement `authenticate` to verify credentials (e.g. validate a JWT).
    Implement `authorize` to enforce access control (e.g. check scopes/roles).

    Register with the app:

        from auth.provider import {ProjectNamePascal}AuthProvider
        app = create_app(auth_provider={ProjectNamePascal}AuthProvider())
    """

    async def authenticate(self, request: Request) -> dict | None:
        token = request.headers.get("authorization", "").removeprefix("Bearer ")
        if not token:
            return None
        # TODO: verify token and return the decoded principal dict
        raise NotImplementedError

    async def authorize(
        self,
        request: Request,
        principal: dict,
        ctx: RequestContext,
    ) -> bool:
        # TODO: implement scope / role checks
        return True
```

Also add an import comment to `src/services/api/main.py` below the existing imports:

```python
# from auth.provider import {ProjectNamePascal}AuthProvider
# app = create_app(auth_provider={ProjectNamePascal}AuthProvider())
```

### 3i — Delete example domain (only if `delete_example` is `yes`)

Remove:
- `src/domains/example/` (entire directory)
- `tests/` files that import from `example` (identify with grep before deleting)

After deletion, remove the `example` scope from `.github/conventional-commits.yml`
and `pr-title.yml`.

Update `infra/labels.tf` if an `example` label exists (it doesn't by default —
skip if absent).

---

## Step 4 — Run validation

After all edits, run the quality gates:

```bash
uv run ruff format --check src/ tests/
uv run ruff check src/ tests/
uv run mypy src/
uv run pytest --no-header -rN --no-cov
```

Report the results. If any gate fails, diagnose and fix before proceeding.

---

## Step 5 — Commit

Stage and commit all changes:

```bash
git add -A
git commit -m "chore: initialise project from blitz template"
```

Do NOT push — leave that to the user once they have verified the result.

---

## Step 6 — Print next steps

Output the following checklist, filling in values from the answers:

```
Project configured. Next steps:

1. cp .env.example .env  (already done if .env did not exist)
   Review .env and fill in any remaining secrets.

2. make install    # installs dependencies via uv sync
   make dev        # starts the server at http://localhost:8000

3. OpenTofu (GitHub repository settings):
   cd infra
   tofu init
   tofu plan       # review what will change
   tofu apply      # requires GITHUB_TOKEN with repo + admin:org scopes

4. Set the following GitHub repository secrets:
   - PYPI_TOKEN     (required for release-please to publish to PyPI)
{auth_step}
{otel_step}

5. Rename / delete src/domains/example/ and replace it with your first domain.
  See CLAUDE.md §Four-layer domain pattern for the full domain structure.

6. Run: make check && make test
   All gates should be green before your first commit to a feature branch.
```

Where:
- `{auth_step}` — if `auth_required=yes`:
  `   Update src/auth/provider.py — implement authenticate() and authorize().`
  Otherwise omit this line.
- `{otel_step}` — if `otel_enabled=yes`:
  `   Confirm OTEL_ENDPOINT in .env points at your collector.`
  Otherwise omit this line.

---

## What NOT to do

- Do not overwrite an existing `.env` — only write it if the file is absent.
- Do not delete `src/domains/example/` without first identifying which test files
  import it — grep first, delete second.
- Do not push the commit — leave pushing to the user.
- Do not generate placeholder secrets or dummy tokens in any file.
- Do not modify files that were not listed in Step 3.
