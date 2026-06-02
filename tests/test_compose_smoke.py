"""Tests for Docker Compose smoke check orchestration."""

from pathlib import Path

from scripts.check_compose_smoke import (
    API_HEALTH_URL,
    WEB_HEALTH_URL,
    build_compose_command,
    run_config_check,
    run_start_smoke,
)


def test_compose_command_uses_smoke_project_and_topology_file() -> None:
    """Verify compose commands target the repository topology safely."""

    root = Path("repository")

    command = build_compose_command(root, "config", "--quiet")

    assert command == (
        "docker",
        "compose",
        "--project-name",
        "tiko-smoke",
        "-f",
        str(root / "infra" / "docker-compose.yml"),
        "config",
        "--quiet",
    )


def test_config_check_runs_compose_config_command() -> None:
    """Verify default smoke mode validates compose configuration."""

    calls: list[tuple[tuple[str, ...], Path]] = []

    def fake_runner(command: tuple[str, ...], cwd: Path) -> int:
        """Record command execution for assertions.

        Args:
            command: Command arguments.
            cwd: Command working directory.

        Returns:
            Simulated success code.
        """

        calls.append((command, cwd))
        return 0

    root = Path("repository")

    assert run_config_check(root, fake_runner) == 0
    assert calls == [(build_compose_command(root, "config", "--quiet"), root)]


def test_start_smoke_runs_up_waits_for_services_and_down() -> None:
    """Verify startup smoke checks health endpoints and tears services down."""

    commands: list[tuple[str, ...]] = []
    urls: list[str] = []

    def fake_runner(command: tuple[str, ...], cwd: Path) -> int:
        """Record compose commands.

        Args:
            command: Command arguments.
            cwd: Command working directory.

        Returns:
            Simulated success code.
        """

        commands.append(command)
        assert cwd == Path("repository")
        return 0

    def fake_waiter(url: str, timeout_seconds: float) -> bool:
        """Record URL polling.

        Args:
            url: URL being polled.
            timeout_seconds: Timeout seconds.

        Returns:
            Simulated readiness.
        """

        urls.append(url)
        assert timeout_seconds == 3.0
        return True

    root = Path("repository")

    assert (
        run_start_smoke(
            root, timeout_seconds=3.0, runner=fake_runner, waiter=fake_waiter
        )
        == 0
    )
    assert commands == [
        build_compose_command(root, "config", "--quiet"),
        build_compose_command(root, "up", "--build", "-d"),
        build_compose_command(root, "down", "--volumes", "--remove-orphans"),
    ]
    assert urls == [API_HEALTH_URL, WEB_HEALTH_URL]


def test_start_smoke_tears_down_when_health_check_fails() -> None:
    """Verify startup smoke cleanup still runs after readiness failure."""

    commands: list[tuple[str, ...]] = []

    def fake_runner(command: tuple[str, ...], cwd: Path) -> int:
        """Record compose commands.

        Args:
            command: Command arguments.
            cwd: Command working directory.

        Returns:
            Simulated success code.
        """

        commands.append(command)
        return 0

    root = Path("repository")

    assert (
        run_start_smoke(root, runner=fake_runner, waiter=lambda url, timeout: False)
        == 1
    )
    assert commands[-1] == build_compose_command(
        root, "down", "--volumes", "--remove-orphans"
    )


def test_start_smoke_tears_down_when_startup_fails() -> None:
    """Verify startup smoke cleanup runs after compose startup failure."""

    commands: list[tuple[str, ...]] = []

    def fake_runner(command: tuple[str, ...], cwd: Path) -> int:
        """Record compose commands and fail startup.

        Args:
            command: Command arguments.
            cwd: Command working directory.

        Returns:
            Simulated command return code.
        """

        commands.append(command)
        return 1 if command[-3:] == ("up", "--build", "-d") else 0

    root = Path("repository")

    assert run_start_smoke(root, runner=fake_runner) == 1
    assert commands == [
        build_compose_command(root, "config", "--quiet"),
        build_compose_command(root, "up", "--build", "-d"),
        build_compose_command(root, "down", "--volumes", "--remove-orphans"),
    ]
