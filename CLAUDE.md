@AGENTS.md

## Claude Code

Project skills and commands live in `.claude/`. Prefer them over improvising:

| Task | Use |
| --- | --- |
| New domain | `/scaffold-domain <name>` (runs `make domain`, then customises) |
| Review a change or domain | `review` skill |
| First-time project setup | `starting-point` skill |
| Auth / audit backend / health check / metric | `/add-auth-provider`, `/add-audit-backend`, `/add-health-check`, `/add-metric` |
| Operational (non-domain) route | `/add-route` |
| Failing request | `/debug-request` |
| Planned feature work | `openspec-propose` → `openspec-apply-change` → `openspec-archive-change` skills |
