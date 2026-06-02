"""Run repository quality gates for local development and CI."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class QualityCheck:
    """Describe one quality gate command.

    Args:
        name: Human-readable check name.
        cwd: Working directory for the command.
        command: Command arguments to execute.
    """

    name: str
    cwd: Path
    command: tuple[str, ...]


QualityCheckRunner = Callable[[QualityCheck], int]


def project_root() -> Path:
    """Return the repository root path.

    Returns:
        Absolute repository root path.
    """

    return Path(__file__).resolve().parents[1]


def build_quality_checks(
    root: Path,
    *,
    include_backend: bool = True,
    include_frontend: bool = True,
) -> list[QualityCheck]:
    """Build selected repository quality checks.

    Args:
        root: Repository root path.
        include_backend: Whether backend checks should be included.
        include_frontend: Whether frontend checks should be included.

    Returns:
        Ordered quality checks.
    """

    checks: list[QualityCheck] = []
    if include_backend:
        checks.extend(
            [
                QualityCheck(
                    "backend format",
                    root,
                    (
                        "uv",
                        "run",
                        "ruff",
                        "format",
                        "--check",
                        "tiko",
                        "tests",
                        "scripts",
                    ),
                ),
                QualityCheck(
                    "backend lint",
                    root,
                    ("uv", "run", "ruff", "check", "tiko", "tests", "scripts"),
                ),
                QualityCheck(
                    "backend typecheck",
                    root,
                    ("uv", "run", "mypy", "tiko", "tests", "scripts"),
                ),
                QualityCheck(
                    "backend tests",
                    root,
                    ("uv", "run", "pytest", "tests", "-W", "error"),
                ),
            ]
        )
    if include_frontend:
        frontend_root = root / "app"
        checks.extend(
            [
                QualityCheck(
                    "frontend format",
                    frontend_root,
                    ("pnpm", "exec", "prettier", "--check", "src"),
                ),
                QualityCheck(
                    "frontend lint",
                    frontend_root,
                    ("pnpm", "exec", "eslint", "src"),
                ),
                QualityCheck(
                    "frontend typecheck",
                    frontend_root,
                    ("pnpm", "exec", "tsc", "--noEmit"),
                ),
                QualityCheck(
                    "frontend build",
                    frontend_root,
                    ("pnpm", "build"),
                ),
            ]
        )
    return checks


def run_subprocess_check(check: QualityCheck) -> int:
    """Run one quality check through subprocess.

    Args:
        check: Quality check to run.

    Returns:
        Child process return code.
    """

    command = resolve_command_executable(check.command)
    try:
        completed = subprocess.run(command, cwd=check.cwd, check=False)
    except FileNotFoundError:
        print(f"Missing executable: {check.command[0]}")
        return 127
    return completed.returncode


def resolve_command_executable(command: tuple[str, ...]) -> tuple[str, ...]:
    """Resolve a command executable using the current process path.

    Args:
        command: Command arguments.

    Returns:
        Command arguments with an absolute executable path when available.
    """

    executable = shutil.which(command[0])
    if executable is None:
        return command
    return (executable, *command[1:])


def run_quality_checks(
    checks: Sequence[QualityCheck],
    runner: QualityCheckRunner = run_subprocess_check,
) -> int:
    """Run quality checks and return a combined exit code.

    Args:
        checks: Ordered checks to run.
        runner: Function that executes one check.

    Returns:
        Zero when all checks pass, otherwise one.
    """

    failed_checks: list[str] = []
    for check in checks:
        print(f"==> {check.name}", flush=True)
        return_code = runner(check)
        if return_code != 0:
            failed_checks.append(check.name)

    if failed_checks:
        print("Quality gate failed:", flush=True)
        for name in failed_checks:
            print(f"- {name}", flush=True)
        return 1

    print("Quality gate passed.", flush=True)
    return 0


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    """Parse command-line arguments.

    Args:
        argv: Raw command-line arguments excluding the executable name.

    Returns:
        Parsed arguments.
    """

    parser = argparse.ArgumentParser(
        description="Run repository backend and frontend quality gates."
    )
    suite_group = parser.add_mutually_exclusive_group()
    suite_group.add_argument(
        "--backend-only",
        action="store_true",
        help="Run only backend quality checks.",
    )
    suite_group.add_argument(
        "--frontend-only",
        action="store_true",
        help="Run only frontend quality checks.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the quality gate command.

    Args:
        argv: Optional command-line arguments excluding the executable name.

    Returns:
        Process exit code.
    """

    args = parse_args(sys.argv[1:] if argv is None else argv)
    checks = build_quality_checks(
        project_root(),
        include_backend=not args.frontend_only,
        include_frontend=not args.backend_only,
    )
    return run_quality_checks(checks)


if __name__ == "__main__":
    sys.exit(main())
