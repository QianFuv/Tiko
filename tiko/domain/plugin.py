"""Plugin manifest and registry schemas."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from tiko.domain.base import DomainModel

PluginType = Literal[
    "market_data_connector",
    "data_import",
    "synthetic_market",
    "feature_calculation",
    "event_generation",
    "analysis_tool",
    "report",
    "experiment",
]
PluginStatus = Literal["draft", "validated", "enabled", "archived", "rejected"]
FileSystemAccess = Literal["none", "sandbox", "readonly"]
CredentialScope = Literal["none", "market_data"]


class PluginPermissions(DomainModel):
    """Represent plugin capabilities allowed by sandbox policy."""

    read_market_data: bool = False
    read_portfolio: bool = False
    write_market_events: bool = False
    write_features: bool = False
    write_orders: bool = False
    network_access: bool = False
    file_system_access: FileSystemAccess = "sandbox"
    approved_directories: list[str] = Field(default_factory=list)
    provider_allowlist: list[str] = Field(default_factory=list)
    methods_allowlist: list[str] = Field(default_factory=list)
    rate_limit_per_minute: int | None = Field(default=None, gt=0)
    credential_scope: CredentialScope = "none"
    cpu_time_limit_seconds: int | None = Field(default=None, gt=0)
    memory_limit_mb: int | None = Field(default=None, gt=0)
    wall_time_limit_seconds: int | None = Field(default=None, gt=0)


class PluginManifest(DomainModel):
    """Represent a proposed plugin manifest."""

    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    plugin_type: PluginType
    description: str = Field(min_length=1)
    permissions: PluginPermissions = Field(default_factory=PluginPermissions)
    inputs: list[str] = Field(default_factory=list)
    output_schema: str = Field(min_length=1)
    tests: list[str] = Field(default_factory=list)


class SandboxResult(DomainModel):
    """Represent deterministic plugin sandbox validation output."""

    passed: bool
    violations: list[str]
    warnings: list[str]


class SandboxTestResult(DomainModel):
    """Represent one executed sandbox policy test result."""

    name: str = Field(min_length=1)
    passed: bool
    message: str = Field(min_length=1)


class SandboxTestReport(DomainModel):
    """Represent sandbox policy test execution output."""

    passed: bool
    validation: SandboxResult
    results: list[SandboxTestResult]


class PluginRegistryEntry(DomainModel):
    """Represent a validated plugin registry entry."""

    plugin_id: UUID
    manifest: PluginManifest
    sandbox_result: SandboxResult
    status: PluginStatus
    created_at: datetime
