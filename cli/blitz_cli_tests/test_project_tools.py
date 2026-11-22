"""[tool.blitz] config, template overrides, `blitz info`, `blitz doctor` and `blitz add`."""

import ast

import pytest

from blitz_cli.commands.doctor import Level, diagnose


def _config(root, body):
    pyproject = root / "pyproject.toml"
    pyproject.write_text(pyproject.read_text() + f"\n[tool.blitz]\n{body}\n")


# ── [tool.blitz] ─────────────────────────────────────────────────────────────


def test_default_service_from_config(blitz, root):
    assert blitz("service", "new", "worker").exit_code == 0
    _config(root, 'default-service = "worker"')
    assert blitz("g", "d", "orders").exit_code == 0
    routes = (root / "tests/domains/orders/integration/test_routes.py").read_text()
    assert "from services.worker.domains import DOMAINS" in routes


def test_tests_off_in_config_and_flag_wins(blitz, root):
    _config(root, "tests = false")
    blitz("g", "d", "orders")
    assert not (root / "tests/domains/orders").exists()
    blitz("g", "d", "drafts", "--tests")
    assert (root / "tests/domains/drafts").exists()


@pytest.mark.parametrize(
    ("body", "error"),
    [
        ("colour = 1", "unknown key"),
        ("tests = 'yes'", "must be a bool"),
        ('templates = "missing"', "is not a directory"),
    ],
)
def test_bad_config(blitz, root, body, error):
    _config(root, body)
    result = blitz("g", "d", "orders")
    assert result.exit_code == 1
    assert error in result.output


def test_project_template_replaces_one_file(blitz, root):
    override = root / "templates/domain/src/domains/$name"
    override.mkdir(parents=True)
    (override / "models.py.tmpl").write_text('"""Our own $Entity model."""\n')
    _config(root, 'templates = "templates"')
    assert blitz("g", "d", "orders").exit_code == 0
    assert (root / "src/domains/orders/models.py").read_text().startswith('"""Our own Order')
    assert "class OrdersDomain" in (root / "src/domains/orders/domain.py").read_text()
    shown = blitz("template", "show", "domain").output
    assert "src/domains/$name/models.py  (project)" in shown
    assert "domain (project):" in blitz("template", "list").output


def test_project_template_set_can_extend_builtin(blitz, root):
    custom = root / "templates/domain-lite"
    custom.mkdir(parents=True)
    (custom / "template.toml").write_text(
        'extends = "domain"\nexclude = ["tests/domains/$name/fuzz/test_fuzz.py"]\n'
    )
    _config(root, 'templates = "templates"')
    shown = blitz("template", "show", "domain-lite").output
    assert "fuzz/test_fuzz.py" not in shown
    assert "src/domains/$name/domain.py" in shown


def test_template_cycle_is_an_error(tmp_path):
    from blitz_cli.templates import TemplateError, load

    (tmp_path / "a").mkdir()
    (tmp_path / "a/template.toml").write_text('extends = "a"\n')
    with pytest.raises(TemplateError, match="extends itself"):
        load("a", [tmp_path])


# ── info / doctor ────────────────────────────────────────────────────────────


def test_info(full):
    import re

    output = full("info").output
    assert re.search(r"^fastapi +: \d+\.\d+", output, re.MULTILINE)
    assert re.search(r"^Default service +: api$", output, re.MULTILINE)


def test_doctor_clean_project(full, full_root):
    assert full("g", "d", "orders").exit_code == 0
    result = full("doctor")
    assert result.exit_code == 0, result.output
    assert "0 errors" in result.output


def test_doctor_finds_problems(full, full_root):
    full("g", "d", "orders", "--no-register", "--no-tests")
    (full_root / "src/domains/orders/domain.py").write_text("def bootstrap(boot): ...\n")
    dockerfile = full_root / "src/services/api/Dockerfile"
    dockerfile.write_text(
        dockerfile.read_text().replace("services.api.main", "services.other.main")
    )
    config = full_root / "src/config.py"
    config.write_text(
        config.read_text().replace(
            "    LOG_LEVEL: str", "    SECRET_THING: str = ''\n    LOG_LEVEL: str"
        )
    )

    findings = {(f.level, f.message) for f in diagnose(full_root)}
    assert (Level.error, "bootstrap must be `async def`") in findings
    assert (Level.warning, "not registered with any service") in findings
    assert (Level.warning, "no unit tests in tests/domains/orders/unit/") in findings
    assert (Level.error, "runs services.other.main:app") in findings
    assert (Level.error, "Settings.SECRET_THING is not documented") in findings
    assert full("doctor").exit_code == 1


def test_doctor_strict_fails_on_warnings(full, full_root):
    full("g", "d", "orders", "--no-register")
    assert full("doctor").exit_code == 0
    assert full("doctor", "--strict").exit_code == 1


# ── add ──────────────────────────────────────────────────────────────────────


def test_add_lists_integrations(full):
    output = full("add").output
    assert "redis:" in output
    assert "postgres:" in output


def test_add_redis(full, full_root):
    result = full("add", "redis", "--skip-install")
    assert result.exit_code == 0, result.output
    assert (full_root / "src/store/redis.py").exists()
    config = (full_root / "src/config.py").read_text()
    assert '    REDIS_URL: str = ""\n' in config
    ast.parse(config)
    assert "REDIS_URL=redis://localhost:6379/0" in (full_root / ".env.example").read_text()
    assert "\n  redis:\n    image: redis:7-alpine" in (full_root / "docker-compose.yml").read_text()
    main = (full_root / "src/services/api/main.py").read_text()
    assert "health_checks=[check_redis]" in main
    assert "run yourself: uv add redis>=5.2" in result.output


def test_add_postgres_wires_a_domain(full, full_root):
    full("g", "d", "billing")
    result = full("add", "postgres", "-d", "billing", "--skip-install")
    assert result.exit_code == 0, result.output
    domain = (full_root / "src/domains/billing/domain.py").read_text()
    ast.parse(domain)
    assert "pool = await asyncpg.create_pool(dsn)" in domain
    assert 'store = PostgresStore(pool, Billing, namespace="billing")' in domain
    assert "domain.closers.append(pool.close)" in domain
    assert '"asyncpg.*"' in (full_root / "pyproject.toml").read_text()
    assert "DATABASE_URL: SecretStr = SecretStr" in (full_root / "src/config.py").read_text()


def test_add_again_only_wires_domains(full, full_root):
    full("add", "redis", "--skip-install")
    full("g", "d", "orders")
    env_before = (full_root / ".env.example").read_text()
    result = full("add", "redis", "-d", "orders", "--skip-install")
    assert result.exit_code == 0, result.output
    assert "wiring domains only" in result.output
    assert (full_root / ".env.example").read_text() == env_before
    assert "RedisStore(client, Order" in (full_root / "src/domains/orders/domain.py").read_text()
    assert "already uses redis" in full("add", "redis", "-d", "orders", "--skip-install").output


def test_add_refuses_second_store_and_unknown(full, full_root):
    full("g", "d", "orders")
    full("add", "redis", "-d", "orders", "--skip-install")
    assert "another store" in full("add", "postgres", "-d", "orders", "--skip-install").output
    assert "unknown integration" in full("add", "mongo").output


def test_add_dry_run_writes_nothing(full, full_root):
    before = {p: p.read_text() for p in full_root.rglob("*") if p.is_file()}
    result = full("add", "redis", "--dry-run")
    assert result.exit_code == 0, result.output
    assert "would run uv add" in result.output
    assert {p: p.read_text() for p in full_root.rglob("*") if p.is_file()} == before
