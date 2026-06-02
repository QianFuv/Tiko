"""Tests for package-level import hygiene."""

import subprocess
import sys
from pathlib import Path
from textwrap import dedent

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def run_python_probe(source: str) -> subprocess.CompletedProcess[str]:
    """Run Python source in an isolated interpreter.

    Args:
        source: Python source code to execute.

    Returns:
        Completed subprocess result.
    """

    return subprocess.run(
        [sys.executable, "-c", dedent(source)],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def assert_probe_passes(source: str) -> None:
    """Assert that an isolated Python probe exits successfully.

    Args:
        source: Python source code to execute.
    """

    result = run_python_probe(source)

    assert result.returncode == 0, result.stderr + result.stdout


def test_data_package_defers_connector_imports() -> None:
    """Verify data package imports do not eagerly load connector dependencies."""

    assert_probe_passes(
        """
        import sys
        import tiko.data

        if "tiko.data.connectors" in sys.modules:
            raise SystemExit("connector module imported eagerly")

        from tiko.data import CsvCandleImporter

        if CsvCandleImporter.__name__ != "CsvCandleImporter":
            raise SystemExit("importer export did not resolve")
        if "tiko.data.importers" not in sys.modules:
            raise SystemExit("importer module did not load after importer access")
        if "tiko.data.connectors" in sys.modules:
            raise SystemExit("connector module loaded by importer access")

        from tiko.data import FORBIDDEN_PRIVATE_METHODS

        if "createOrder" not in FORBIDDEN_PRIVATE_METHODS:
            raise SystemExit("connector constant did not resolve")
        if "tiko.data.connectors" not in sys.modules:
            raise SystemExit("connector module did not load after connector access")
        """
    )


def test_services_package_defers_simulation_imports() -> None:
    """Verify service package imports do not eagerly load simulation services."""

    assert_probe_passes(
        """
        import sys
        import tiko.services

        if "tiko.services.simulation" in sys.modules:
            raise SystemExit("simulation service imported eagerly")

        from tiko.services import RiskService

        if RiskService.__name__ != "RiskService":
            raise SystemExit("risk service export did not resolve")
        if "tiko.services.risk" not in sys.modules:
            raise SystemExit("risk service module did not load after access")
        if "tiko.services.simulation" in sys.modules:
            raise SystemExit("simulation service loaded by risk access")

        from tiko.services import SimulationService

        if SimulationService.__name__ != "SimulationService":
            raise SystemExit("simulation service export did not resolve")
        if "tiko.services.simulation" not in sys.modules:
            raise SystemExit("simulation service did not load after access")
        """
    )
