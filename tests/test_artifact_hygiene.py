"""Tests for distribution artifact hygiene checks."""

from pathlib import Path
from zipfile import ZipFile

from scripts.check_artifact_hygiene import main, scan_zip_artifact


def write_zip(path: Path, entries: dict[str, str | bytes]) -> None:
    """Write a zip file with deterministic test entries.

    Args:
        path: Zip file path.
        entries: Entry names mapped to text or byte payloads.
    """

    with ZipFile(path, "w") as archive:
        for name, payload in entries.items():
            archive.writestr(name, payload)


def violation_reasons(path: Path) -> list[str]:
    """Return formatted violation reasons for one zip artifact.

    Args:
        path: Zip artifact path.

    Returns:
        Redacted violation messages.
    """

    return [violation.format() for violation in scan_zip_artifact(path)]


def test_safe_zip_artifact_passes(tmp_path: Path) -> None:
    """Verify normal source files and placeholder env examples pass."""

    artifact = tmp_path / "safe.zip"
    write_zip(
        artifact,
        {
            "README.md": "TIKO_OPENROUTER_API_KEY=...",
            ".env.example": "TIKO_OPENROUTER_API_KEY=your-openrouter-key\n",
            "tiko/__init__.py": '"""Package."""\n',
        },
    )

    assert violation_reasons(artifact) == []


def test_local_env_file_is_rejected(tmp_path: Path) -> None:
    """Verify local environment files are denied."""

    artifact = tmp_path / "unsafe.zip"
    write_zip(artifact, {".env": "TIKO_OPENROUTER_API_KEY=redacted-test-key\n"})

    assert violation_reasons(artifact) == [
        ".env: contains local env file",
        ".env: contains secret-like assignment for TIKO_OPENROUTER_API_KEY",
    ]


def test_secret_assignment_is_rejected_without_printing_value(tmp_path: Path) -> None:
    """Verify secret-like values fail without leaking the value in output."""

    artifact = tmp_path / "unsafe.zip"
    secret_value = "sk-test-secret-value"
    write_zip(artifact, {"config.txt": f"OPENAI_API_KEY={secret_value}\n"})

    violations = violation_reasons(artifact)

    assert violations == [
        "config.txt: contains secret-like assignment for OPENAI_API_KEY"
    ]
    assert secret_value not in "\n".join(violations)


def test_generated_cache_files_are_rejected(tmp_path: Path) -> None:
    """Verify Python caches and TypeScript build metadata are denied."""

    artifact = tmp_path / "unsafe.zip"
    write_zip(
        artifact,
        {
            "tiko/__pycache__/main.cpython-312.pyc": b"cache",
            "app/tsconfig.tsbuildinfo": "{}",
        },
    )

    violations = violation_reasons(artifact)

    assert (
        "tiko/__pycache__/main.cpython-312.pyc: "
        "contains generated directory __pycache__"
    ) in violations
    assert (
        "tiko/__pycache__/main.cpython-312.pyc: contains generated file suffix .pyc"
    ) in violations
    assert (
        "app/tsconfig.tsbuildinfo: contains generated file suffix .tsbuildinfo"
    ) in violations


def test_command_returns_failure_for_unsafe_artifact(tmp_path: Path) -> None:
    """Verify the command-line entry point fails unsafe artifacts."""

    artifact = tmp_path / "unsafe.zip"
    write_zip(artifact, {"secrets.env": "API_TOKEN=real-token-value\n"})

    assert main([str(artifact)]) == 1
