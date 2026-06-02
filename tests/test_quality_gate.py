"""Tests for repository quality gate orchestration."""

from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.check_quality import (
    QualityCheck,
    build_quality_checks,
    parse_args,
    resolve_command_executable,
    run_quality_checks,
)


def check_names(checks: list[QualityCheck]) -> list[str]:
    """Return quality check names.

    Args:
        checks: Quality checks.

    Returns:
        Check names in order.
    """

    return [check.name for check in checks]


def test_default_quality_gate_selects_backend_and_frontend_checks() -> None:
    """Verify default quality gate coverage includes backend and frontend checks."""

    root = Path("repository")

    checks = build_quality_checks(root)

    assert check_names(checks) == [
        "backend format",
        "backend lint",
        "backend typecheck",
        "backend tests",
        "frontend format",
        "frontend lint",
        "frontend typecheck",
        "frontend build",
    ]
    assert checks[0].cwd == root
    assert checks[0].command == (
        "uv",
        "run",
        "ruff",
        "format",
        "--check",
        "tiko",
        "tests",
        "scripts",
    )
    assert checks[-1].cwd == root / "app"
    assert checks[-1].command == ("pnpm", "build")


def test_backend_only_quality_gate_filters_frontend_checks() -> None:
    """Verify backend-only selection excludes frontend checks."""

    checks = build_quality_checks(
        Path("repository"), include_backend=True, include_frontend=False
    )

    assert check_names(checks) == [
        "backend format",
        "backend lint",
        "backend typecheck",
        "backend tests",
    ]


def test_frontend_only_quality_gate_filters_backend_checks() -> None:
    """Verify frontend-only selection excludes backend checks."""

    checks = build_quality_checks(
        Path("repository"), include_backend=False, include_frontend=True
    )

    assert check_names(checks) == [
        "frontend format",
        "frontend lint",
        "frontend typecheck",
        "frontend build",
    ]


def test_quality_gate_reports_failed_checks(capsys: pytest.CaptureFixture[str]) -> None:
    """Verify failed child commands make the gate fail after all checks run."""

    checks = [
        QualityCheck("first", Path("repository"), ("first",)),
        QualityCheck("second", Path("repository"), ("second",)),
    ]
    called_checks: list[str] = []

    def fake_runner(check: QualityCheck) -> int:
        """Record check calls and fail the second check.

        Args:
            check: Quality check under test.

        Returns:
            Simulated return code.
        """

        called_checks.append(check.name)
        return 1 if check.name == "second" else 0

    result = run_quality_checks(checks, fake_runner)

    assert result == 1
    assert called_checks == ["first", "second"]
    assert "Quality gate failed:" in capsys.readouterr().out


def test_quality_gate_reports_success(capsys: pytest.CaptureFixture[str]) -> None:
    """Verify successful child commands make the gate pass."""

    checks = [QualityCheck("first", Path("repository"), ("first",))]

    assert run_quality_checks(checks, lambda check: 0) == 0
    assert "Quality gate passed." in capsys.readouterr().out


def test_quality_gate_cli_flags_are_mutually_exclusive() -> None:
    """Verify backend-only and frontend-only flags cannot be combined."""

    with pytest.raises(SystemExit) as error:
        parse_args(["--backend-only", "--frontend-only"])

    assert error.value.code == 2


def test_quality_gate_resolves_platform_executables() -> None:
    """Verify platform-specific executable paths are used when available."""

    with patch("scripts.check_quality.shutil.which", return_value="C:\\bin\\pnpm.cmd"):
        command = resolve_command_executable(("pnpm", "exec", "eslint", "src"))

    assert command == ("C:\\bin\\pnpm.cmd", "exec", "eslint", "src")


def test_quality_gate_keeps_missing_executables_unresolved() -> None:
    """Verify missing executable names are preserved for subprocess errors."""

    with patch("scripts.check_quality.shutil.which", return_value=None):
        command = resolve_command_executable(("missing-tool", "--version"))

    assert command == ("missing-tool", "--version")
