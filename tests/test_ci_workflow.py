"""Tests for the GitHub Actions quality workflow."""

from pathlib import Path
from typing import cast

import yaml


def load_quality_workflow() -> dict[str, object]:
    """Load the quality workflow without YAML boolean coercion.

    Returns:
        Parsed workflow document.
    """

    with Path(".github/workflows/quality.yml").open(encoding="utf-8") as file:
        workflow = yaml.load(file, Loader=yaml.BaseLoader)
    assert isinstance(workflow, dict)
    return cast(dict[str, object], workflow)


def require_mapping(value: object) -> dict[str, object]:
    """Require a string-keyed mapping.

    Args:
        value: Parsed YAML value.

    Returns:
        The value cast to a string-keyed mapping.
    """

    assert isinstance(value, dict)
    return cast(dict[str, object], value)


def require_list(value: object) -> list[object]:
    """Require a list value.

    Args:
        value: Parsed YAML value.

    Returns:
        The value cast to a list.
    """

    assert isinstance(value, list)
    return value


def quality_job() -> dict[str, object]:
    """Return the quality workflow job.

    Returns:
        Quality job definition.
    """

    workflow = load_quality_workflow()
    jobs = require_mapping(workflow["jobs"])
    return require_mapping(jobs["quality"])


def quality_steps() -> list[dict[str, object]]:
    """Return quality workflow steps.

    Returns:
        Step definitions.
    """

    steps = require_list(quality_job()["steps"])
    assert all(isinstance(step, dict) for step in steps)
    return cast(list[dict[str, object]], steps)


def test_quality_workflow_runs_on_code_and_manual_events() -> None:
    """Verify CI triggers include code changes and manual dispatch."""

    workflow = load_quality_workflow()
    triggers = require_mapping(workflow["on"])

    assert set(triggers) == {"push", "pull_request", "workflow_dispatch"}
    assert require_mapping(workflow["permissions"]) == {"contents": "read"}


def test_quality_workflow_uses_current_setup_actions() -> None:
    """Verify CI setup actions use current major versions."""

    uses = [step["uses"] for step in quality_steps() if "uses" in step]

    assert uses == [
        "actions/checkout@v6",
        "pnpm/action-setup@v6",
        "actions/setup-node@v6",
        "actions/setup-python@v6",
    ]


def test_quality_workflow_runs_local_gates_and_compose_smoke() -> None:
    """Verify CI runs repository-local quality and smoke commands."""

    run_steps = [step for step in quality_steps() if "run" in step]
    commands = [step["run"] for step in run_steps]

    assert "uv sync --extra dev --frozen" in commands
    assert "pnpm install --frozen-lockfile" in commands
    assert "uv run python scripts/check_quality.py" in commands
    assert (
        "uv run python scripts/check_compose_smoke.py --start --timeout-seconds 120"
        in commands
    )
    frontend_install = next(
        step for step in run_steps if step["run"] == "pnpm install --frozen-lockfile"
    )
    assert frontend_install["working-directory"] == "app"
