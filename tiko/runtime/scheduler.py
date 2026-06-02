"""Long-running runtime scheduler process helpers."""

import json
import time
from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Literal
from uuid import UUID

from tiko.api.dependencies import get_runtime_service, get_simulation_service
from tiko.core.config import get_settings
from tiko.domain.reporting import Alert, ReportArtifact
from tiko.domain.runtime import WatchdogReport
from tiko.services.runtime import RuntimeService
from tiko.services.simulation import SimulationService
from tiko.simulation.state import SimulationStepResult

ScheduledReportInterval = Literal["daily", "weekly"]
DEFAULT_SCHEDULED_REPORT_INTERVALS: tuple[ScheduledReportInterval, ...] = (
    "daily",
    "weekly",
)


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

    def tick_scheduled_reports(
        self,
        intervals: Sequence[
            ScheduledReportInterval
        ] = DEFAULT_SCHEDULED_REPORT_INTERVALS,
    ) -> tuple[ReportArtifact, ...]:
        """Create due scheduler-managed simulation reports.

        Args:
            intervals: Scheduled report intervals to evaluate.

        Returns:
            Reports created by this scheduler tick.
        """

        if self._simulation_service is None:
            return ()
        created_reports: list[ReportArtifact] = []
        for run in self._simulation_service.list_runs():
            if run.status != "running":
                continue
            for interval in intervals:
                period_key = self._scheduled_report_period_key(
                    run.current_sim_time,
                    interval,
                )
                if self._has_scheduled_report(run.run_id, interval, period_key):
                    continue
                created_reports.append(
                    self._simulation_service.create_simulation_report(
                        run.run_id,
                        automation_metadata={
                            "source": "scheduler",
                            "interval": interval,
                            "period_key": period_key,
                            "simulated_time": run.current_sim_time.isoformat(),
                        },
                    )
                )
        return tuple(created_reports)

    def _has_scheduled_report(
        self,
        run_id: UUID,
        interval: ScheduledReportInterval,
        period_key: str,
    ) -> bool:
        """Return whether a scheduled report already exists.

        Args:
            run_id: Simulation run identifier.
            interval: Scheduled report interval.
            period_key: Simulated period key.

        Returns:
            `True` when the report already exists.
        """

        if self._simulation_service is None:
            return False
        for report in self._simulation_service.list_reports(run_id):
            automation_section = report.sections.get("automation")
            if not isinstance(automation_section, dict):
                continue
            if (
                automation_section.get("source") == "scheduler"
                and automation_section.get("interval") == interval
                and automation_section.get("period_key") == period_key
            ):
                return True
        return False

    def _scheduled_report_period_key(
        self,
        simulated_time: datetime,
        interval: ScheduledReportInterval,
    ) -> str:
        """Build a deterministic simulated period key.

        Args:
            simulated_time: Current simulated time.
            interval: Scheduled report interval.

        Returns:
            Period key for de-duplication.
        """

        if interval == "daily":
            return simulated_time.date().isoformat()
        iso_calendar = simulated_time.isocalendar()
        return f"{iso_calendar.year}-W{iso_calendar.week:02d}"


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


def run_scheduler_loop(
    service: RuntimeService,
    simulation_service: SimulationService | None,
    interval_seconds: float,
    max_iterations: int | None = None,
    sleep: Callable[[float], None] = time.sleep,
    on_report: Callable[[WatchdogReport], None] | None = None,
) -> tuple[WatchdogReport, ...]:
    """Run scheduler ticks until stopped.

    Args:
        service: Runtime service used for watchdog checks.
        simulation_service: Optional simulation service advanced by clock ticks.
        interval_seconds: Delay between scheduler ticks.
        max_iterations: Optional upper bound for tests.
        sleep: Sleep function used between ticks.
        on_report: Optional callback receiving each watchdog report.

    Returns:
        Watchdog reports for bounded runs.

    Raises:
        ValueError: If loop settings are invalid.
    """

    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be greater than zero.")
    if max_iterations is not None and max_iterations < 1:
        raise ValueError("max_iterations must be at least one when provided.")

    scheduler = RuntimeScheduler(service, simulation_service)
    reports: list[WatchdogReport] = []
    iteration = 0
    while max_iterations is None or iteration < max_iterations:
        scheduler.tick_simulation_clock()
        scheduler.tick_scheduled_reports()
        report = scheduler.tick()
        if on_report is not None:
            on_report(report)
        if max_iterations is not None:
            reports.append(report)
        iteration += 1
        if max_iterations is None or iteration < max_iterations:
            sleep(interval_seconds)
    return tuple(reports)


def main() -> int:
    """Run the scheduler loop and print JSON watchdog reports.

    Returns:
        Process exit code.
    """

    settings = get_settings()

    def print_report(report: WatchdogReport) -> None:
        """Print one watchdog report as JSON.

        Args:
            report: Watchdog report from one scheduler tick.
        """

        print(json.dumps(report.model_dump(mode="json"), sort_keys=True), flush=True)

    try:
        run_scheduler_loop(
            service=get_runtime_service(),
            simulation_service=get_simulation_service(),
            interval_seconds=settings.scheduler_interval_seconds,
            on_report=print_report,
        )
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
