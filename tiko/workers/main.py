"""One-shot worker heartbeat process helpers."""

import json
from collections.abc import Callable, Mapping, Sequence

from tiko.domain.runtime import BackgroundJob, JobType, WorkerHeartbeat
from tiko.services.runtime import RuntimeService
from tiko.workers import agent_worker, backtest_worker, report_worker, rl_worker
from tiko.workers.definitions import WorkerDefinition, WorkerExecutionResult

JobHandler = Callable[[BackgroundJob], dict[str, object]]


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


def build_default_job_handlers() -> dict[JobType, JobHandler]:
    """Build deterministic placeholder handlers for supported job types.

    Returns:
        Default runtime job handlers keyed by job type.
    """

    return {
        "agent_inference": build_placeholder_job_result,
        "backtest": build_placeholder_job_result,
        "experiment_run": build_placeholder_job_result,
        "report_generation": build_placeholder_job_result,
        "rl_training": rl_worker.handle_training_job,
    }


def build_placeholder_job_result(job: BackgroundJob) -> dict[str, object]:
    """Build a deterministic placeholder result for a runtime job.

    Args:
        job: Claimed runtime job.

    Returns:
        Structured placeholder result metadata.
    """

    return {
        "message": "Worker completed deterministic placeholder job.",
        "job_type": job.job_type,
        "resource_type": job.resource_type,
        "resource_id": job.resource_id,
    }


def process_worker_jobs(
    service: RuntimeService,
    definition: WorkerDefinition,
    handlers: Mapping[JobType, JobHandler] | None = None,
    max_jobs: int = 1,
) -> WorkerExecutionResult:
    """Process queued jobs supported by one worker definition.

    Args:
        service: Runtime service containing queued jobs.
        definition: Worker role definition.
        handlers: Optional handlers keyed by runtime job type.
        max_jobs: Maximum jobs to claim during this execution pass.

    Returns:
        Structured execution summary.

    Raises:
        ValueError: If `max_jobs` is less than one.
    """

    if max_jobs < 1:
        raise ValueError("max_jobs must be at least one.")

    job_handlers = handlers if handlers is not None else build_default_job_handlers()
    initial_queue_depth = service.count_queued_jobs(definition.job_types)
    service.record_heartbeat(
        worker_name=definition.worker_name,
        worker_status="healthy",
        event_queue_depth=initial_queue_depth,
        clock_lag_ms=0,
    )

    claimed_job_ids = []
    completed_job_ids = []
    failed_job_ids = []

    for _ in range(max_jobs):
        job = service.claim_next_job(
            worker_name=definition.worker_name,
            job_types=definition.job_types,
        )
        if job is None:
            break
        claimed_job_ids.append(job.job_id)
        handler = job_handlers.get(job.job_type)
        if handler is None:
            failed_job = service.fail_job(
                job.job_id,
                f"No handler registered for job type {job.job_type}.",
            )
            failed_job_ids.append(failed_job.job_id)
            continue
        try:
            result = handler(job)
        except Exception as error:
            failed_job = service.fail_job(job.job_id, str(error))
            failed_job_ids.append(failed_job.job_id)
        else:
            completed_job = service.complete_job(job.job_id, result)
            completed_job_ids.append(completed_job.job_id)

    remaining_queue_depth = service.count_queued_jobs(definition.job_types)
    service.record_heartbeat(
        worker_name=definition.worker_name,
        worker_status="healthy",
        event_queue_depth=remaining_queue_depth,
        clock_lag_ms=0,
    )
    return WorkerExecutionResult(
        worker_name=definition.worker_name,
        claimed_job_ids=tuple(claimed_job_ids),
        completed_job_ids=tuple(completed_job_ids),
        failed_job_ids=tuple(failed_job_ids),
        remaining_queue_depth=remaining_queue_depth,
    )


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
