"""Plugin sandbox policy validation."""

from tiko.domain.plugin import PluginManifest, SandboxResult


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
        if len(permissions.provider_allowlist) == 0:
            violations.append("Network plugins require a provider allowlist.")
    if manifest.plugin_type == "market_data_connector" and permissions.write_features:
        warnings.append("Market data connectors should not write features directly.")
    if len(manifest.tests) == 0:
        violations.append("Plugin manifests must declare sandbox tests.")
    return SandboxResult(
        passed=len(violations) == 0,
        violations=violations,
        warnings=warnings,
    )
