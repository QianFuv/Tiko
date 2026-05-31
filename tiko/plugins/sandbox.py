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
    "test_network_policy",
}


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
    if manifest.plugin_type == "market_data_connector" and permissions.write_features:
        warnings.append("Market data connectors should not write features directly.")
    if len(manifest.tests) == 0:
        violations.append("Plugin manifests must declare sandbox tests.")
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
        return SandboxTestResult(
            name=test_name,
            passed=True,
            message="Manifest schema is valid.",
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
    return SandboxTestResult(
        name=test_name,
        passed=False,
        message=(
            f"Unsupported sandbox test '{test_name}'. Supported tests: "
            f"{', '.join(sorted(SUPPORTED_SANDBOX_TESTS))}."
        ),
    )


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
