# blitz CLI

`blitz` generates code from predefined templates and manages the project's boilerplate:
domains, services and their registration. It is its own uv project (own lock and `.venv`),
so neither typer nor the templates end up in the service images.

```bash
uv run --project cli blitz --help      # from the repository root (or `make cli ARGS=--help`)
```

| Command | Does |
| --- | --- |
| `blitz domain new <name> [--entity E] [--service api] [--no-register] [--dry-run]` | Render the `domain` template into `src/domains/<name>/` + `tests/domains/<name>/`, add it to the service's `DOMAINS` |
| `blitz domain list` | Domains, the services serving them, whether they have tests |
| `blitz domain remove <name> [--yes]` | Delete the package and its tests; unregister it from every service |
| `blitz service new <name> [--dry-run]` | Render the `service` template into `src/services/<name>/` |
| `blitz service list` | Services and the domains each serves |
| `blitz template list` / `show <set>` | Template sets, their placeholders and output files |

The project root is the nearest directory above the current one with `pyproject.toml` and
`src/services/`; pass `--root` to override. Nothing is ever overwritten: a command that would
replace a file stops before writing. Generated Python is import-sorted and formatted with the
project's Ruff config.

## Templates

`blitz_cli/templates/<set>/` mirrors the project layout. Every `*.tmpl` file is rendered with
Python's `string.Template`: `$name` / `${Entity}` placeholders in both the path and the content,
`$$` for a literal `$`, and the `.tmpl` suffix dropped. `template.toml` holds the set's
`description`.

| Set | Placeholders |
| --- | --- |
| `domain` | `name`, `route`, `Plural`, `Entity`, `entity`, `entity_words`, `service` |
| `service` | `service` |

To change what every new domain or service starts with, edit its template; a test checks
that the CLI supplies a value for every placeholder.

## Development

```bash
cd cli && make verify      # format check, lint, mypy --strict, tests (also run by the root `make verify`)
```
