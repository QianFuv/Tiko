"""One-shot worker heartbeat process helpers."""

import json
from collections.abc import Sequence

from tiko.domain.runtime import WorkerHeartbeat
from tiko.services.runtime import RuntimeService
from tiko.workers import agent_worker, backtest_worker, report_worker, rl_worker
from tiko.workers.definitions import WorkerDefinition


def build_worker_definitions() -> tuple[WorkerDefinition, ...]:
    """Build all known worker role definitions.

    Returns:
        Worker definitions for runtime process roles.
    """

    return (
        agent_worker.build_definition(),
        backtest_worker.build_definition(),
        rl_worker.build_definition(),
        report_worker.build_definition(),
    )


def record_worker_heartbeats(
    service: RuntimeService,
    definitions: Sequence[WorkerDefinition] | None = None,
) -> list[WorkerHeartbeat]:
    """Record healthy heartbeats for worker process roles.

    Args:
        service: Runtime service receiving heartbeat records.
        definitions: Optional worker definitions. All known definitions are used
            when omitted.

    Returns:
        Recorded worker heartbeats.
    """

    worker_definitions = (
        tuple(definitions) if definitions is not None else build_worker_definitions()
    )
    return [
        service.record_heartbeat(
            worker_name=definition.worker_name,
            worker_status="healthy",
            event_queue_depth=0,
            clock_lag_ms=0,
        )
        for definition in worker_definitions
    ]


def main() -> int:
    """Record one heartbeat for each worker role and print JSON output.

    Returns:
        Process exit code.
    """

    service = RuntimeService()
    heartbeats = record_worker_heartbeats(service)
    payload = [heartbeat.model_dump(mode="json") for heartbeat in heartbeats]
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
