"""One-shot runtime scheduler process helpers."""

import json
from datetime import datetime

from tiko.domain.reporting import Alert
from tiko.domain.runtime import WatchdogReport
from tiko.services.runtime import RuntimeService
from tiko.services.simulation import SimulationService
from tiko.simulation.state import SimulationStepResult


class RuntimeScheduler:
    """Run deterministic scheduler checks against runtime state."""

    def __init__(
        self,
        service: RuntimeService,
        simulation_service: SimulationService | None = None,
    ) -> None:
        """Initialize the scheduler.

        Args:
            service: Runtime service used for watchdog checks.
            simulation_service: Optional simulation service advanced by clock ticks.
        """

        self._service = service
        self._simulation_service = simulation_service

    def tick(self) -> WatchdogReport:
        """Run one scheduler tick.

        Returns:
            Watchdog report for current runtime state.
        """

        if self._simulation_service is None:
            return self._service.run_watchdog()
        runs = self._simulation_service.list_runs()
        return self._service.run_watchdog(
            simulation_runs=runs,
            alerts=self._list_simulation_alerts(),
            orders=self._simulation_service.list_orders(),
        )

    def _list_simulation_alerts(self) -> list[Alert]:
        """List alerts available to scheduler watchdog checks.

        Returns:
            Alerts from all known simulation runs.
        """

        if self._simulation_service is None:
            return []
        alerts: list[Alert] = []
        for run in self._simulation_service.list_runs():
            try:
                alerts.extend(self._simulation_service.list_alerts(run.run_id))
            except KeyError:
                continue
        return alerts

    def tick_simulation_clock(
        self,
        now: datetime | None = None,
    ) -> tuple[SimulationStepResult, ...]:
        """Advance due running simulations for one scheduler tick.

        Args:
            now: Optional wall-clock evaluation time.

        Returns:
            Step results produced by the scheduler tick.
        """

        if self._simulation_service is None:
            return ()
        return tuple(self._simulation_service.advance_running_runs(now=now))


def run_scheduler_once(service: RuntimeService | None = None) -> WatchdogReport:
    """Run a single scheduler watchdog pass.

    Args:
        service: Optional runtime service. A fresh service is used when omitted.

    Returns:
        Watchdog report for the scheduler pass.
    """

    runtime_service = service if service is not None else RuntimeService()
    return RuntimeScheduler(runtime_service).tick()


def run_simulation_clock_once(
    simulation_service: SimulationService,
    now: datetime | None = None,
) -> tuple[SimulationStepResult, ...]:
    """Run one scheduler pass for live simulated clock advancement.

    Args:
        simulation_service: Simulation service containing runs to advance.
        now: Optional wall-clock evaluation time.

    Returns:
        Step results produced by the scheduler tick.
    """

    return RuntimeScheduler(
        service=RuntimeService(),
        simulation_service=simulation_service,
    ).tick_simulation_clock(now=now)


def main() -> int:
    """Run one scheduler pass and print a JSON watchdog report.

    Returns:
        Process exit code.
    """

    report = run_scheduler_once()
    print(json.dumps(report.model_dump(mode="json"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
