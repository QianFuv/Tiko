"""Tests for deployment topology configuration."""

import tomllib
from pathlib import Path
from typing import cast

import yaml

REQUIRED_SERVICES = {
    "web",
    "api",
    "worker",
    "scheduler",
    "postgres",
    "redis",
    "object-store",
}
PROCESS_SERVICES = {"api", "worker", "scheduler"}


def load_compose_file() -> dict[str, object]:
    """Load the Docker compose topology.

    Returns:
        Parsed compose document.
    """

    with Path("infra/docker-compose.yml").open(encoding="utf-8") as file:
        document = yaml.safe_load(file)
    assert isinstance(document, dict)
    return cast(dict[str, object], document)


def require_mapping(value: object) -> dict[str, object]:
    """Require a mapping value from parsed configuration.

    Args:
        value: Parsed configuration value.

    Returns:
        The value cast to a string-keyed mapping.
    """

    assert isinstance(value, dict)
    return cast(dict[str, object], value)


def require_string_list(value: object) -> list[str]:
    """Require a string list value from parsed configuration.

    Args:
        value: Parsed configuration value.

    Returns:
        The value cast to a list of strings.
    """

    assert isinstance(value, list)
    assert all(isinstance(item, str) for item in value)
    return cast(list[str], value)


def get_service(compose: dict[str, object], service_name: str) -> dict[str, object]:
    """Get one compose service definition.

    Args:
        compose: Parsed compose document.
        service_name: Service name to read.

    Returns:
        Compose service definition.
    """

    services = require_mapping(compose["services"])
    return require_mapping(services[service_name])


def test_compose_defines_architecture_services_and_volumes() -> None:
    """Verify compose includes the architecture deployment roles."""

    compose = load_compose_file()
    services = require_mapping(compose["services"])
    volumes = require_mapping(compose["volumes"])

    assert set(services) >= REQUIRED_SERVICES
    assert {"pgdata", "objectdata"} <= set(volumes)


def test_process_services_use_simulation_only_safety_flags() -> None:
    """Verify process services cannot opt into live trading from compose."""

    compose = load_compose_file()

    for service_name in PROCESS_SERVICES:
        service = get_service(compose, service_name)
        environment = require_mapping(service["environment"])

        assert environment["TIKO_SAFETY_MODE"] == "simulation_only"
        assert environment["TIKO_ALLOW_PRIVATE_EXCHANGE_METHODS"] == "false"
        assert environment["TIKO_ALLOW_TRADING_CREDENTIALS"] == "false"
        assert "TIKO_OPENROUTER_API_KEY" not in environment
        assert "OPENROUTER_API_KEY" not in environment


def test_process_services_share_api_image_with_role_commands() -> None:
    """Verify API, worker, and scheduler use the same build target safely."""

    compose = load_compose_file()
    api = get_service(compose, "api")
    worker = get_service(compose, "worker")
    scheduler = get_service(compose, "scheduler")

    assert require_mapping(api["build"]) == {
        "context": "..",
        "dockerfile": "infra/api.Dockerfile",
    }
    assert worker["build"] == api["build"]
    assert scheduler["build"] == api["build"]
    assert worker["command"] == [".venv/bin/python", "-m", "tiko.workers.main"]
    assert scheduler["command"] == [
        ".venv/bin/python",
        "-m",
        "tiko.runtime.scheduler",
    ]


def test_frontend_topology_uses_next_standalone_server() -> None:
    """Verify frontend container uses the Next.js standalone server."""

    next_config = Path("app/next.config.ts").read_text(encoding="utf-8")
    dockerfile = Path("app/Dockerfile").read_text(encoding="utf-8")
    web = get_service(load_compose_file(), "web")

    assert 'output: "standalone"' in next_config
    assert 'CMD ["node", "server.js"]' in dockerfile
    assert require_mapping(web["build"]) == {
        "context": "../app",
        "dockerfile": "Dockerfile",
    }
    assert require_mapping(web["environment"])["NEXT_PUBLIC_API_BASE_URL"] == (
        "http://localhost:8000"
    )


def test_postgresql_driver_dependency_matches_compose_url() -> None:
    """Verify PostgreSQL compose URL has a matching Python driver."""

    with Path("pyproject.toml").open("rb") as file:
        project = tomllib.load(file)
    dependencies = require_string_list(
        require_mapping(project["project"])["dependencies"]
    )
    api_environment = require_mapping(
        get_service(load_compose_file(), "api")["environment"]
    )

    assert any(dependency.startswith("psycopg[binary]") for dependency in dependencies)
    assert str(api_environment["TIKO_DATABASE_URL"]).startswith("postgresql+psycopg://")


def test_redis_driver_dependency_matches_compose_url() -> None:
    """Verify Redis compose URL has a matching Python driver."""

    with Path("pyproject.toml").open("rb") as file:
        project = tomllib.load(file)
    dependencies = require_string_list(
        require_mapping(project["project"])["dependencies"]
    )
    compose = load_compose_file()

    assert any(dependency.startswith("redis") for dependency in dependencies)
    for service_name in PROCESS_SERVICES:
        environment = require_mapping(get_service(compose, service_name)["environment"])
        assert str(environment["TIKO_REDIS_URL"]).startswith("redis://")
