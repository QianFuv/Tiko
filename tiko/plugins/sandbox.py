"""Plugin sandbox policy validation."""

from tiko.data import FORBIDDEN_PRIVATE_METHODS
from tiko.domain.plugin import (
    PluginManifest,
    SandboxResult,
    SandboxTestReport,
    SandboxTestResult,
)

SUPPORTED_SANDBOX_TESTS = {
    "test_schema_valid",
    "test_no_write_orders",
    "test_no_secret_inputs",
    "test_no_future_events",
    "test_deterministic_seed",
    "test_network_policy",
    "test_credential_scope",
    "test_approved_directories",
    "test_resource_limits",
}
SUPPORTED_OUTPUT_SCHEMAS = {
    "AnalysisReport",
    "Candle",
    "Candle[]",
    "ExperimentResult",
    "FeatureSnapshot",
    "FeatureSnapshot[]",
    "MarketEvent",
    "OrderBookSnapshot",
    "OrderBookSnapshot[]",
    "ReportArtifact",
}
TIME_BOUND_INPUTS = {"as_of", "current_sim_time", "simulated_time"}
DETERMINISTIC_SEED_INPUTS = {"deterministic_seed", "random_seed", "seed"}
STOCHASTIC_PLUGIN_TYPES = {"event_generation", "experiment", "synthetic_market"}
FORBIDDEN_SECRET_INPUT_PATTERNS = {
    "apikey",
    "api_key",
    "credential",
    "password",
    "privatekey",
    "private_key",
    "secret",
    "token",
}
FORBIDDEN_ENV_INPUT_SEGMENTS = {"env", "environment"}


def validate_plugin_manifest(manifest: PluginManifest) -> SandboxResult:
    """Validate a plugin manifest against architecture sandbox policy.

    Args:
        manifest: Plugin manifest to validate.

    Returns:
        Sandbox validation result.
    """

    violations: list[str] = []
    warnings: list[str] = []
    permissions = manifest.permissions
    if permissions.write_orders:
        violations.append("Plugins cannot request write_orders permission.")
    violations.extend(_secret_input_violations(manifest))
    if permissions.network_access:
        if manifest.plugin_type != "market_data_connector":
            violations.append(
                "Network access is restricted to read-only market data connectors."
            )
        if not permissions.read_market_data:
            violations.append("Network plugins must request read_market_data only.")
        if (
            permissions.read_portfolio
            or permissions.write_market_events
            or permissions.write_features
        ):
            violations.append("Network plugins must only request read_market_data.")
        if len(permissions.provider_allowlist) == 0:
            violations.append("Network plugins require a provider allowlist.")
        if len(permissions.methods_allowlist) == 0:
            violations.append("Network plugins require a methods allowlist.")
        forbidden_methods = _forbidden_network_methods(permissions.methods_allowlist)
        if forbidden_methods:
            violations.append(
                "Network plugin methods are not allowed: "
                f"{', '.join(forbidden_methods)}."
            )
        if permissions.rate_limit_per_minute is None:
            violations.append(
                "Network plugins require a positive rate_limit_per_minute."
            )
    violations.extend(_credential_scope_violations(manifest))
    violations.extend(_directory_policy_violations(manifest))
    violations.extend(_resource_limit_violations(manifest))
    if manifest.plugin_type == "market_data_connector" and permissions.write_features:
        warnings.append("Market data connectors should not write features directly.")
    if len(manifest.tests) == 0:
        violations.append("Plugin manifests must declare sandbox tests.")
    elif "test_schema_valid" not in manifest.tests:
        violations.append("Plugin manifests must declare test_schema_valid.")
    return SandboxResult(
        passed=len(violations) == 0,
        violations=violations,
        warnings=warnings,
    )


def run_plugin_sandbox_tests(manifest: PluginManifest) -> SandboxTestReport:
    """Run deterministic sandbox policy tests declared by a plugin manifest.

    Args:
        manifest: Plugin manifest to test.

    Returns:
        Sandbox test execution report.
    """

    validation = validate_plugin_manifest(manifest)
    results = [_run_sandbox_test(manifest, test_name) for test_name in manifest.tests]
    return SandboxTestReport(
        passed=validation.passed and all(result.passed for result in results),
        validation=validation,
        results=results,
    )


def _run_sandbox_test(
    manifest: PluginManifest,
    test_name: str,
) -> SandboxTestResult:
    """Run one supported sandbox test by name.

    Args:
        manifest: Plugin manifest under test.
        test_name: Declared sandbox test name.

    Returns:
        Sandbox test result.
    """

    if test_name == "test_schema_valid":
        passed = _schema_policy_passes(manifest)
        return SandboxTestResult(
            name=test_name,
            passed=passed,
            message=(
                "Manifest output schema is supported."
                if passed
                else "Manifest output_schema is not supported by the sandbox."
            ),
        )
    if test_name == "test_no_write_orders":
        passed = not manifest.permissions.write_orders
        return SandboxTestResult(
            name=test_name,
            passed=passed,
            message=(
                "Plugin does not request order-writing permission."
                if passed
                else "Plugin requested forbidden order-writing permission."
            ),
        )
    if test_name == "test_no_secret_inputs":
        passed = _secret_input_policy_passes(manifest)
        return SandboxTestResult(
            name=test_name,
            passed=passed,
            message=(
                "Plugin inputs do not request environment or secret values."
                if passed
                else "Plugin inputs request forbidden environment or secret values."
            ),
        )
    if test_name == "test_no_future_events":
        passed = _future_event_policy_passes(manifest)
        return SandboxTestResult(
            name=test_name,
            passed=passed,
            message=(
                "Event output is bounded by point-in-time inputs."
                if passed
                else "MarketEvent output requires an as-of or simulated-time input."
            ),
        )
    if test_name == "test_deterministic_seed":
        passed = _deterministic_seed_policy_passes(manifest)
        return SandboxTestResult(
            name=test_name,
            passed=passed,
            message=(
                "Plugin declares a deterministic seed input."
                if passed
                else "Stochastic plugin types require a deterministic seed input."
            ),
        )
    if test_name == "test_network_policy":
        passed = _network_policy_passes(manifest)
        return SandboxTestResult(
            name=test_name,
            passed=passed,
            message=(
                "Network policy is compatible with sandbox rules."
                if passed
                else "Network access violates sandbox rules."
            ),
        )
    if test_name == "test_credential_scope":
        passed = _credential_scope_passes(manifest)
        return SandboxTestResult(
            name=test_name,
            passed=passed,
            message=(
                "Credential scope is compatible with sandbox rules."
                if passed
                else "Credential scope violates sandbox rules."
            ),
        )
    if test_name == "test_approved_directories":
        passed = _directory_policy_passes(manifest)
        return SandboxTestResult(
            name=test_name,
            passed=passed,
            message=(
                "File-system access is constrained to approved directories."
                if passed
                else "File-system access violates approved directory policy."
            ),
        )
    if test_name == "test_resource_limits":
        passed = _resource_limits_pass(manifest)
        return SandboxTestResult(
            name=test_name,
            passed=passed,
            message=(
                "CPU, memory, and wall-time limits are declared."
                if passed
                else "Plugin resource limits are incomplete."
            ),
        )
    return SandboxTestResult(
        name=test_name,
        passed=False,
        message=(
            f"Unsupported sandbox test '{test_name}'. Supported tests: "
            f"{', '.join(sorted(SUPPORTED_SANDBOX_TESTS))}."
        ),
    )


def _schema_policy_passes(manifest: PluginManifest) -> bool:
    """Return whether the manifest output schema is supported.

    Args:
        manifest: Plugin manifest under validation.

    Returns:
        Whether the output schema is part of the platform schema allowlist.
    """

    return manifest.output_schema in SUPPORTED_OUTPUT_SCHEMAS


def _future_event_policy_passes(manifest: PluginManifest) -> bool:
    """Return whether event output is bounded by point-in-time inputs.

    Args:
        manifest: Plugin manifest under validation.

    Returns:
        Whether the manifest can be checked for future-event safety.
    """

    if manifest.output_schema != "MarketEvent":
        return True
    return bool(set(manifest.inputs).intersection(TIME_BOUND_INPUTS))


def _deterministic_seed_policy_passes(manifest: PluginManifest) -> bool:
    """Return whether stochastic plugin output has a deterministic seed input.

    Args:
        manifest: Plugin manifest under validation.

    Returns:
        Whether deterministic-seed policy passes.
    """

    if manifest.plugin_type not in STOCHASTIC_PLUGIN_TYPES:
        return True
    return bool(set(manifest.inputs).intersection(DETERMINISTIC_SEED_INPUTS))


def _secret_input_violations(manifest: PluginManifest) -> list[str]:
    """Validate plugin inputs for forbidden secret-like values.

    Args:
        manifest: Plugin manifest under validation.

    Returns:
        Secret input policy violation messages.
    """

    forbidden_inputs = sorted(
        {
            input_name
            for input_name in manifest.inputs
            if _is_forbidden_secret_input(input_name)
        }
    )
    if not forbidden_inputs:
        return []
    return [
        "Plugin manifest inputs cannot request environment or secret values: "
        f"{', '.join(forbidden_inputs)}."
    ]


def _directory_policy_violations(manifest: PluginManifest) -> list[str]:
    """Validate plugin approved-directory policy.

    Args:
        manifest: Plugin manifest under validation.

    Returns:
        Directory policy violation messages.
    """

    permissions = manifest.permissions
    violations: list[str] = []
    if (
        permissions.file_system_access != "none"
        and len(permissions.approved_directories) == 0
    ):
        violations.append(
            "Plugins with file system access require approved_directories."
        )
    unsafe_directories = [
        directory
        for directory in permissions.approved_directories
        if not _is_safe_sandbox_directory(directory)
    ]
    if unsafe_directories:
        violations.append(
            "Plugin approved_directories contain unsafe paths: "
            f"{', '.join(sorted(unsafe_directories))}."
        )
    return violations


def _resource_limit_violations(manifest: PluginManifest) -> list[str]:
    """Validate plugin resource limit policy.

    Args:
        manifest: Plugin manifest under validation.

    Returns:
        Resource limit policy violation messages.
    """

    permissions = manifest.permissions
    missing_limits: list[str] = []
    if permissions.cpu_time_limit_seconds is None:
        missing_limits.append("cpu_time_limit_seconds")
    if permissions.memory_limit_mb is None:
        missing_limits.append("memory_limit_mb")
    if permissions.wall_time_limit_seconds is None:
        missing_limits.append("wall_time_limit_seconds")
    if not missing_limits:
        return []
    return [
        "Plugin manifests require positive resource limits: "
        f"{', '.join(missing_limits)}."
    ]


def _credential_scope_violations(manifest: PluginManifest) -> list[str]:
    """Validate plugin credential scope policy.

    Args:
        manifest: Plugin manifest under validation.

    Returns:
        Credential scope policy violation messages.
    """

    permissions = manifest.permissions
    if permissions.credential_scope == "none":
        return []
    if (
        manifest.plugin_type == "market_data_connector"
        and permissions.network_access
        and permissions.read_market_data
    ):
        return []
    return [
        "Plugin credential_scope is restricted to read-only network market data "
        "connectors."
    ]


def _directory_policy_passes(manifest: PluginManifest) -> bool:
    """Return whether approved-directory policy passes.

    Args:
        manifest: Plugin manifest under validation.

    Returns:
        Whether directory policy passes.
    """

    return not _directory_policy_violations(manifest)


def _resource_limits_pass(manifest: PluginManifest) -> bool:
    """Return whether resource limit policy passes.

    Args:
        manifest: Plugin manifest under validation.

    Returns:
        Whether resource limit policy passes.
    """

    return not _resource_limit_violations(manifest)


def _credential_scope_passes(manifest: PluginManifest) -> bool:
    """Return whether credential scope policy passes.

    Args:
        manifest: Plugin manifest under validation.

    Returns:
        Whether credential scope policy passes.
    """

    return not _credential_scope_violations(manifest)


def _secret_input_policy_passes(manifest: PluginManifest) -> bool:
    """Return whether plugin input policy passes.

    Args:
        manifest: Plugin manifest under validation.

    Returns:
        Whether secret input policy passes.
    """

    return not _secret_input_violations(manifest)


def _is_forbidden_secret_input(input_name: str) -> bool:
    """Return whether a manifest input appears to request secrets.

    Args:
        input_name: Manifest input name.

    Returns:
        Whether the input name is forbidden by secret-input policy.
    """

    normalized = _normalize_manifest_input(input_name)
    segments = {segment for segment in normalized.split("_") if segment}
    if segments.intersection(FORBIDDEN_ENV_INPUT_SEGMENTS):
        return True
    return any(pattern in normalized for pattern in FORBIDDEN_SECRET_INPUT_PATTERNS)


def _normalize_manifest_input(input_name: str) -> str:
    """Normalize a manifest input name for policy matching.

    Args:
        input_name: Manifest input name.

    Returns:
        Lowercase input name with punctuation represented as underscores.
    """

    return "".join(
        character.lower() if character.isalnum() else "_"
        for character in input_name.strip()
    )


def _is_safe_sandbox_directory(directory: str) -> bool:
    """Return whether a directory path is sandbox-relative and non-traversing.

    Args:
        directory: Directory path from the plugin manifest.

    Returns:
        `True` when the path is safe for sandbox allowlisting.
    """

    normalized = directory.replace("\\", "/").strip()
    if not normalized or normalized.startswith("/") or ":" in normalized:
        return False
    segments = [segment for segment in normalized.split("/") if segment]
    return bool(segments) and ".." not in segments


def _network_policy_passes(manifest: PluginManifest) -> bool:
    """Evaluate sandbox network policy for one manifest.

    Args:
        manifest: Plugin manifest under test.

    Returns:
        Whether the manifest satisfies network policy rules.
    """

    permissions = manifest.permissions
    if not permissions.network_access:
        return True
    return (
        manifest.plugin_type == "market_data_connector"
        and permissions.read_market_data
        and len(permissions.provider_allowlist) > 0
        and len(permissions.methods_allowlist) > 0
        and not _forbidden_network_methods(permissions.methods_allowlist)
        and permissions.rate_limit_per_minute is not None
        and not permissions.read_portfolio
        and not permissions.write_market_events
        and not permissions.write_features
        and not permissions.write_orders
    )


def _forbidden_network_methods(methods: list[str]) -> list[str]:
    """List forbidden private methods requested by a network plugin.

    Args:
        methods: Requested network method allowlist.

    Returns:
        Forbidden private methods present in the allowlist.
    """

    return sorted(set(methods).intersection(FORBIDDEN_PRIVATE_METHODS))
