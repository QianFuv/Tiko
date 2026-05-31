"""Tests for plugin sandbox policy validation."""

from tiko.domain.plugin import PluginManifest, PluginPermissions
from tiko.plugins import validate_plugin_manifest


def create_safe_manifest() -> PluginManifest:
    """Create a safe plugin manifest fixture.

    Returns:
        Safe plugin manifest.
    """

    return PluginManifest(
        name="synthetic_liquidity_shock_generator",
        version="0.1.0",
        plugin_type="event_generation",
        description="Generate synthetic liquidity shocks for simulations.",
        permissions=PluginPermissions(write_market_events=True),
        inputs=["run_id", "symbols"],
        output_schema="MarketEvent",
        tests=["test_schema_valid"],
    )


def test_sandbox_accepts_safe_simulation_plugin() -> None:
    """Verify sandbox accepts a safe non-network plugin manifest."""

    result = validate_plugin_manifest(create_safe_manifest())

    assert result.passed is True
    assert result.violations == []


def test_sandbox_rejects_order_writing_plugin() -> None:
    """Verify plugins cannot request order-writing permission."""

    manifest = create_safe_manifest().model_copy(
        update={
            "permissions": PluginPermissions(
                write_market_events=True,
                write_orders=True,
            )
        }
    )

    result = validate_plugin_manifest(manifest)

    assert result.passed is False
    assert "write_orders" in result.violations[0]


def test_sandbox_restricts_network_to_allowlisted_market_data() -> None:
    """Verify network access requires read-only market data allowlisting."""

    unsafe_manifest = create_safe_manifest().model_copy(
        update={
            "permissions": PluginPermissions(
                read_market_data=True,
                network_access=True,
            )
        }
    )
    safe_manifest = create_safe_manifest().model_copy(
        update={
            "plugin_type": "market_data_connector",
            "permissions": PluginPermissions(
                read_market_data=True,
                network_access=True,
                provider_allowlist=["binance"],
            ),
        }
    )

    unsafe_result = validate_plugin_manifest(unsafe_manifest)
    safe_result = validate_plugin_manifest(safe_manifest)

    assert unsafe_result.passed is False
    assert safe_result.passed is True


def test_sandbox_requires_manifest_tests() -> None:
    """Verify plugin manifests must declare sandbox tests."""

    manifest = create_safe_manifest().model_copy(update={"tests": []})

    result = validate_plugin_manifest(manifest)

    assert result.passed is False
    assert "tests" in result.violations[0]
