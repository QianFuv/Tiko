"""Tests for plugin sandbox policy validation."""

from tiko.domain.plugin import PluginManifest, PluginPermissions
from tiko.plugins import run_plugin_sandbox_tests, validate_plugin_manifest


def create_safe_permissions(**overrides: object) -> PluginPermissions:
    """Create safe plugin permissions for sandbox tests.

    Args:
        **overrides: Permission field overrides.

    Returns:
        Safe plugin permissions.
    """

    values = {
        "write_market_events": True,
        "approved_directories": ["plugins/synthetic_liquidity_shock_generator"],
        "cpu_time_limit_seconds": 10,
        "memory_limit_mb": 128,
        "wall_time_limit_seconds": 30,
    } | overrides
    return PluginPermissions.model_validate(values)


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
        permissions=create_safe_permissions(),
        inputs=["run_id", "symbols", "current_sim_time", "seed"],
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
        update={"permissions": create_safe_permissions(write_orders=True)}
    )

    result = validate_plugin_manifest(manifest)

    assert result.passed is False
    assert "write_orders" in result.violations[0]


def test_sandbox_restricts_network_to_allowlisted_market_data() -> None:
    """Verify network access requires read-only market data allowlisting."""

    unsafe_manifest = create_safe_manifest().model_copy(
        update={
            "permissions": create_safe_permissions(
                read_market_data=True,
                network_access=True,
            )
        }
    )
    safe_manifest = create_safe_manifest().model_copy(
        update={
            "plugin_type": "market_data_connector",
            "permissions": create_safe_permissions(
                write_market_events=False,
                read_market_data=True,
                network_access=True,
                provider_allowlist=["binance"],
                methods_allowlist=["fetchTicker"],
                rate_limit_per_minute=60,
                credential_scope="market_data",
            ),
        }
    )

    unsafe_result = validate_plugin_manifest(unsafe_manifest)
    safe_result = validate_plugin_manifest(safe_manifest)

    assert unsafe_result.passed is False
    assert any(
        "provider allowlist" in violation for violation in unsafe_result.violations
    )
    assert any(
        "methods allowlist" in violation for violation in unsafe_result.violations
    )
    assert safe_result.passed is True


def test_sandbox_rejects_network_private_methods_and_missing_rate_limit() -> None:
    """Verify network plugins must be method-bounded and rate-limited."""

    private_method_manifest = create_safe_manifest().model_copy(
        update={
            "plugin_type": "market_data_connector",
            "permissions": create_safe_permissions(
                write_market_events=False,
                read_market_data=True,
                network_access=True,
                provider_allowlist=["binance"],
                methods_allowlist=["fetchBalance"],
                rate_limit_per_minute=60,
                credential_scope="market_data",
            ),
        }
    )
    missing_rate_limit_manifest = create_safe_manifest().model_copy(
        update={
            "plugin_type": "market_data_connector",
            "permissions": create_safe_permissions(
                write_market_events=False,
                read_market_data=True,
                network_access=True,
                provider_allowlist=["binance"],
                methods_allowlist=["fetchTicker"],
                credential_scope="market_data",
            ),
        }
    )

    private_method_result = validate_plugin_manifest(private_method_manifest)
    missing_rate_limit_result = validate_plugin_manifest(missing_rate_limit_manifest)

    assert private_method_result.passed is False
    assert any(
        "fetchBalance" in violation for violation in private_method_result.violations
    )
    assert missing_rate_limit_result.passed is False
    assert any(
        "rate_limit_per_minute" in violation
        for violation in missing_rate_limit_result.violations
    )


def test_sandbox_requires_approved_directories_for_file_access() -> None:
    """Verify file-system access requires explicit safe directory allowlists."""

    missing_directory_manifest = create_safe_manifest().model_copy(
        update={"permissions": create_safe_permissions(approved_directories=[])}
    )
    unsafe_directory_manifest = create_safe_manifest().model_copy(
        update={"permissions": create_safe_permissions(approved_directories=["../tmp"])}
    )
    disabled_file_access_manifest = create_safe_manifest().model_copy(
        update={
            "permissions": create_safe_permissions(
                file_system_access="none",
                approved_directories=[],
            )
        }
    )

    missing_directory_result = validate_plugin_manifest(missing_directory_manifest)
    unsafe_directory_result = validate_plugin_manifest(unsafe_directory_manifest)
    disabled_file_access_result = validate_plugin_manifest(
        disabled_file_access_manifest
    )

    assert missing_directory_result.passed is False
    assert any(
        "approved_directories" in violation
        for violation in missing_directory_result.violations
    )
    assert unsafe_directory_result.passed is False
    assert any(
        "../tmp" in violation for violation in unsafe_directory_result.violations
    )
    assert disabled_file_access_result.passed is True


def test_sandbox_requires_resource_limits() -> None:
    """Verify plugins declare CPU, memory, and wall-time limits."""

    manifest = create_safe_manifest().model_copy(
        update={
            "permissions": create_safe_permissions(
                cpu_time_limit_seconds=None,
                memory_limit_mb=None,
            )
        }
    )

    result = validate_plugin_manifest(manifest)

    assert result.passed is False
    assert any("cpu_time_limit_seconds" in violation for violation in result.violations)
    assert any("memory_limit_mb" in violation for violation in result.violations)


def test_sandbox_requires_time_bound_event_tests() -> None:
    """Verify MarketEvent plugins declare point-in-time input boundaries."""

    missing_time_manifest = create_safe_manifest().model_copy(
        update={
            "inputs": ["run_id", "symbols", "seed"],
            "tests": ["test_no_future_events"],
        }
    )
    bounded_manifest = create_safe_manifest().model_copy(
        update={"tests": ["test_no_future_events"]}
    )
    non_event_manifest = create_safe_manifest().model_copy(
        update={
            "plugin_type": "analysis_tool",
            "permissions": create_safe_permissions(write_market_events=False),
            "inputs": ["run_id"],
            "output_schema": "AnalysisReport",
            "tests": ["test_no_future_events"],
        }
    )

    missing_time_report = run_plugin_sandbox_tests(missing_time_manifest)
    bounded_report = run_plugin_sandbox_tests(bounded_manifest)
    non_event_report = run_plugin_sandbox_tests(non_event_manifest)

    assert missing_time_report.passed is False
    assert "simulated-time" in missing_time_report.results[0].message
    assert bounded_report.passed is True
    assert non_event_report.passed is True


def test_sandbox_requires_deterministic_seed_for_stochastic_plugins() -> None:
    """Verify stochastic plugins expose deterministic seed inputs."""

    missing_seed_manifest = create_safe_manifest().model_copy(
        update={
            "inputs": ["run_id", "symbols", "current_sim_time"],
            "tests": ["test_deterministic_seed"],
        }
    )
    seeded_manifest = create_safe_manifest().model_copy(
        update={"tests": ["test_deterministic_seed"]}
    )
    analysis_manifest = create_safe_manifest().model_copy(
        update={
            "plugin_type": "analysis_tool",
            "permissions": create_safe_permissions(write_market_events=False),
            "inputs": ["run_id"],
            "output_schema": "AnalysisReport",
            "tests": ["test_deterministic_seed"],
        }
    )

    missing_seed_report = run_plugin_sandbox_tests(missing_seed_manifest)
    seeded_report = run_plugin_sandbox_tests(seeded_manifest)
    analysis_report = run_plugin_sandbox_tests(analysis_manifest)

    assert missing_seed_report.passed is False
    assert "deterministic seed" in missing_seed_report.results[0].message
    assert seeded_report.passed is True
    assert analysis_report.passed is True


def test_sandbox_requires_manifest_tests() -> None:
    """Verify plugin manifests must declare sandbox tests."""

    manifest = create_safe_manifest().model_copy(update={"tests": []})

    result = validate_plugin_manifest(manifest)

    assert result.passed is False
    assert "tests" in result.violations[0]


def test_sandbox_executes_supported_manifest_tests() -> None:
    """Verify sandbox test execution reports per-test evidence."""

    manifest = create_safe_manifest().model_copy(
        update={
            "tests": [
                "test_schema_valid",
                "test_no_write_orders",
                "test_no_future_events",
                "test_deterministic_seed",
                "test_network_policy",
                "test_approved_directories",
                "test_resource_limits",
            ]
        }
    )

    report = run_plugin_sandbox_tests(manifest)

    assert report.passed is True
    assert report.validation.passed is True
    assert [result.name for result in report.results] == [
        "test_schema_valid",
        "test_no_write_orders",
        "test_no_future_events",
        "test_deterministic_seed",
        "test_network_policy",
        "test_approved_directories",
        "test_resource_limits",
    ]
    assert all(result.passed for result in report.results)


def test_sandbox_test_report_flags_forbidden_order_writes() -> None:
    """Verify sandbox test execution fails unsafe order-writing manifests."""

    manifest = create_safe_manifest().model_copy(
        update={
            "permissions": create_safe_permissions(write_orders=True),
            "tests": ["test_no_write_orders"],
        }
    )

    report = run_plugin_sandbox_tests(manifest)

    assert report.passed is False
    assert report.validation.passed is False
    assert report.results[0].passed is False
    assert "order-writing" in report.results[0].message


def test_sandbox_test_report_fails_unsupported_tests() -> None:
    """Verify unsupported declared sandbox tests fail explicitly."""

    manifest = create_safe_manifest().model_copy(
        update={"tests": ["test_unknown_policy"]}
    )

    report = run_plugin_sandbox_tests(manifest)

    assert report.passed is False
    assert report.validation.passed is True
    assert report.results[0].name == "test_unknown_policy"
    assert report.results[0].passed is False
    assert "Unsupported sandbox test" in report.results[0].message
