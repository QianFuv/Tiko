"""Check distribution archives for secrets and generated artifacts."""

from __future__ import annotations

import argparse
import re
import sys
import zipfile
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

DENIED_PATH_COMPONENTS = {
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".next",
    "node_modules",
}
DENIED_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".tsbuildinfo",
}
SECRET_ASSIGNMENT_PATTERN = re.compile(
    r"(?im)^\s*(?:export\s+)?"
    r"([A-Z0-9_]*(?:API_KEY|PRIVATE_KEY|SECRET|TOKEN|PASSWORD)[A-Z0-9_]*)"
    r"\s*=\s*([^\r\n#]+)"
)
PRIVATE_KEY_BLOCK_PATTERN = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")
TEXT_SCAN_LIMIT_BYTES = 1_000_000


@dataclass(frozen=True)
class HygieneViolation:
    """Describe one unsafe artifact entry without exposing secret values."""

    path: str
    reason: str

    def format(self) -> str:
        """Format the violation for command-line output.

        Returns:
            Redacted violation message.
        """

        return f"{self.path}: {self.reason}"


def scan_zip_artifact(path: Path) -> list[HygieneViolation]:
    """Scan a zip artifact for unsafe files and secret-like content.

    Args:
        path: Zip artifact path.

    Returns:
        Hygiene violations found in the artifact.
    """

    violations: list[HygieneViolation] = []
    with zipfile.ZipFile(path) as archive:
        for member in archive.infolist():
            entry_name = member.filename
            violations.extend(scan_entry_name(entry_name))
            if member.is_dir() or member.file_size > TEXT_SCAN_LIMIT_BYTES:
                continue
            payload = archive.read(member)
            text = decode_text_payload(payload)
            if text is None:
                continue
            violations.extend(scan_text_content(entry_name, text))
    return violations


def scan_entry_name(entry_name: str) -> list[HygieneViolation]:
    """Scan an archive entry path for denied generated or secret files.

    Args:
        entry_name: Zip entry path.

    Returns:
        Path hygiene violations.
    """

    normalized = entry_name.replace("\\", "/")
    path = PurePosixPath(normalized)
    violations: list[HygieneViolation] = []
    components = set(path.parts)
    denied_components = components & DENIED_PATH_COMPONENTS
    for component in sorted(denied_components):
        violations.append(
            HygieneViolation(normalized, f"contains generated directory {component}")
        )
    file_name = path.name
    if is_denied_environment_file(file_name):
        violations.append(HygieneViolation(normalized, "contains local env file"))
    if path.suffix in DENIED_SUFFIXES:
        violations.append(
            HygieneViolation(
                normalized, f"contains generated file suffix {path.suffix}"
            )
        )
    return violations


def scan_text_content(entry_name: str, text: str) -> list[HygieneViolation]:
    """Scan text content for secret-like assignments.

    Args:
        entry_name: Zip entry path.
        text: Decoded text payload.

    Returns:
        Redacted content hygiene violations.
    """

    violations: list[HygieneViolation] = []
    if PRIVATE_KEY_BLOCK_PATTERN.search(text):
        violations.append(HygieneViolation(entry_name, "contains private key block"))
    for match in SECRET_ASSIGNMENT_PATTERN.finditer(text):
        variable_name = match.group(1)
        value = normalize_assignment_value(match.group(2))
        if is_placeholder_secret_value(value):
            continue
        violations.append(
            HygieneViolation(
                entry_name,
                f"contains secret-like assignment for {variable_name}",
            )
        )
    return violations


def is_denied_environment_file(file_name: str) -> bool:
    """Return whether a file name is a local environment file.

    Args:
        file_name: Base file name.

    Returns:
        `True` when the name should not appear in a distribution artifact.
    """

    if file_name == ".env":
        return True
    if file_name == ".env.example":
        return False
    return file_name.startswith(".env.")


def decode_text_payload(payload: bytes) -> str | None:
    """Decode a zip entry payload when it appears to be text.

    Args:
        payload: Zip entry bytes.

    Returns:
        Decoded text or `None` for binary payloads.
    """

    if b"\x00" in payload:
        return None
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError:
        return None


def normalize_assignment_value(value: str) -> str:
    """Normalize an assignment value before placeholder checks.

    Args:
        value: Raw assignment value.

    Returns:
        Trimmed and unquoted value.
    """

    trimmed = value.strip()
    if len(trimmed) >= 2 and trimmed[0] == trimmed[-1] and trimmed[0] in {"'", '"'}:
        return trimmed[1:-1].strip()
    return trimmed


def is_placeholder_secret_value(value: str) -> bool:
    """Return whether a secret-like value is a safe placeholder.

    Args:
        value: Normalized assignment value.

    Returns:
        `True` when the value is clearly not real key material.
    """

    lowered = value.lower()
    if value == "" or value == "...":
        return True
    placeholder_fragments = (
        "your-",
        "placeholder",
        "example",
        "changeme",
        "replace-me",
        "<",
        ">",
    )
    return any(fragment in lowered for fragment in placeholder_fragments)


def scan_artifacts(paths: Iterable[Path]) -> list[HygieneViolation]:
    """Scan all artifact paths.

    Args:
        paths: Candidate artifact paths.

    Returns:
        Combined hygiene violations.
    """

    violations: list[HygieneViolation] = []
    for path in paths:
        if path.suffix.lower() != ".zip":
            violations.append(HygieneViolation(str(path), "unsupported artifact type"))
            continue
        violations.extend(scan_zip_artifact(path))
    return violations


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    """Parse command-line arguments.

    Args:
        argv: Raw command-line arguments excluding executable name.

    Returns:
        Parsed arguments.
    """

    parser = argparse.ArgumentParser(
        description="Fail when distribution artifacts contain secrets or caches."
    )
    parser.add_argument(
        "artifacts",
        nargs="+",
        type=Path,
        help="Zip artifacts to scan.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the artifact hygiene checker.

    Args:
        argv: Optional command-line arguments.

    Returns:
        Process exit code.
    """

    args = parse_args(sys.argv[1:] if argv is None else argv)
    violations = scan_artifacts(args.artifacts)
    if not violations:
        print("Artifact hygiene check passed.")
        return 0
    print("Artifact hygiene check failed:")
    for violation in violations:
        print(f"- {violation.format()}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
