"""Run Docker Compose topology smoke checks."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from pathlib import Path

COMPOSE_PROJECT_NAME = "tiko-smoke"
DEFAULT_TIMEOUT_SECONDS = 120.0
DEFAULT_POLL_SECONDS = 2.0
API_HEALTH_URL = "http://127.0.0.1:8000/api/health"
WEB_HEALTH_URL = "http://127.0.0.1:3000/healthz"

CommandRunner = Callable[[tuple[str, ...], Path], int]
UrlWaiter = Callable[[str, float], bool]


def project_root() -> Path:
    """Return the repository root path.

    Returns:
        Absolute repository root path.
    """

    return Path(__file__).resolve().parents[1]


def build_compose_command(root: Path, *args: str) -> tuple[str, ...]:
    """Build a Docker Compose command for the repository topology.

    Args:
        root: Repository root path.
        args: Docker Compose subcommand arguments.

    Returns:
        Docker Compose command arguments.
    """

    return (
        "docker",
        "compose",
        "--project-name",
        COMPOSE_PROJECT_NAME,
        "-f",
        str(root / "infra" / "docker-compose.yml"),
        *args,
    )


def run_subprocess_command(command: tuple[str, ...], cwd: Path) -> int:
    """Run a command and return its exit code.

    Args:
        command: Command arguments.
        cwd: Command working directory.

    Returns:
        Command return code.
    """

    resolved_command = resolve_command_executable(command)
    try:
        completed = subprocess.run(resolved_command, cwd=cwd, check=False)
    except FileNotFoundError:
        print(f"Missing executable: {command[0]}", flush=True)
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


def run_config_check(
    root: Path,
    runner: CommandRunner = run_subprocess_command,
) -> int:
    """Run daemon-free Docker Compose configuration validation.

    Args:
        root: Repository root path.
        runner: Command execution function.

    Returns:
        Command return code.
    """

    return runner(build_compose_command(root, "config", "--quiet"), root)


def wait_for_http_ok(
    url: str,
    timeout_seconds: float,
    poll_seconds: float = DEFAULT_POLL_SECONDS,
) -> bool:
    """Wait for a URL to return a successful HTTP response.

    Args:
        url: URL to poll.
        timeout_seconds: Maximum time to wait.
        poll_seconds: Delay between attempts.

    Returns:
        `True` when the URL responds with a 2xx status before timeout.
    """

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=poll_seconds) as response:
                if 200 <= response.getcode() < 300:
                    return True
        except (OSError, urllib.error.URLError):
            pass
        time.sleep(poll_seconds)
    return False


def run_start_smoke(
    root: Path,
    *,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    runner: CommandRunner = run_subprocess_command,
    waiter: UrlWaiter = wait_for_http_ok,
) -> int:
    """Run a Docker Compose startup smoke test.

    Args:
        root: Repository root path.
        timeout_seconds: Maximum wait time for each health endpoint.
        runner: Command execution function.
        waiter: HTTP polling function.

    Returns:
        Zero when services start and health checks pass, otherwise one.
    """

    config_result = run_config_check(root, runner)
    if config_result != 0:
        return config_result

    up_result = runner(build_compose_command(root, "up", "--build", "-d"), root)
    if up_result != 0:
        down_result = runner(
            build_compose_command(root, "down", "--volumes", "--remove-orphans"),
            root,
        )
        return down_result if down_result != 0 else up_result

    smoke_result = 0
    try:
        if not waiter(API_HEALTH_URL, timeout_seconds):
            print(f"Timed out waiting for {API_HEALTH_URL}", flush=True)
            smoke_result = 1
        if not waiter(WEB_HEALTH_URL, timeout_seconds):
            print(f"Timed out waiting for {WEB_HEALTH_URL}", flush=True)
            smoke_result = 1
    finally:
        down_result = runner(
            build_compose_command(root, "down", "--volumes", "--remove-orphans"),
            root,
        )
    return down_result if down_result != 0 else smoke_result


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    """Parse command-line arguments.

    Args:
        argv: Raw command-line arguments excluding the executable name.

    Returns:
        Parsed arguments.
    """

    parser = argparse.ArgumentParser(
        description="Run Docker Compose config validation or startup smoke checks."
    )
    parser.add_argument(
        "--start",
        action="store_true",
        help="Build and start the compose topology before health checks.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="Maximum wait time for each health endpoint in start mode.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the Docker Compose smoke command.

    Args:
        argv: Optional command-line arguments excluding the executable name.

    Returns:
        Process exit code.
    """

    args = parse_args(sys.argv[1:] if argv is None else argv)
    root = project_root()
    if args.start:
        return run_start_smoke(root, timeout_seconds=args.timeout_seconds)
    return run_config_check(root)


if __name__ == "__main__":
    sys.exit(main())
