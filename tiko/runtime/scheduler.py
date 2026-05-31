"""One-shot runtime scheduler process helpers."""

import json

from tiko.domain.runtime import WatchdogReport
from tiko.services.runtime import RuntimeService


class RuntimeScheduler:
    """Run deterministic scheduler checks against runtime state."""

    def __init__(self, service: RuntimeService) -> None:
        """Initialize the scheduler.

        Args:
            service: Runtime service used for watchdog checks.
        """

        self._service = service

    def tick(self) -> WatchdogReport:
        """Run one scheduler tick.

        Returns:
            Watchdog report for current runtime state.
        """

        return self._service.run_watchdog()


def run_scheduler_once(service: RuntimeService | None = None) -> WatchdogReport:
    """Run a single scheduler watchdog pass.

    Args:
        service: Optional runtime service. A fresh service is used when omitted.

    Returns:
        Watchdog report for the scheduler pass.
    """

    runtime_service = service if service is not None else RuntimeService()
    return RuntimeScheduler(runtime_service).tick()


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
