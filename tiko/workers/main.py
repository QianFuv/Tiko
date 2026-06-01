"""Long-running worker process helpers."""

import json
import time
from collections.abc import Callable, Mapping, Sequence
from uuid import UUID

from tiko.api.dependencies import get_runtime_service
from tiko.core.config import get_settings
from tiko.domain.runtime import BackgroundJob, JobType, WorkerHeartbeat
from tiko.services.runtime import RuntimeService
from tiko.workers import agent_worker, backtest_worker, report_worker, rl_worker
from tiko.workers.definitions import WorkerDefinition, WorkerExecutionResult

JobHandler = Callable[[BackgroundJob], dict[str, object]]
JobFinishedHandler = Callable[[BackgroundJob], None]


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
    """Build default handlers for supported job types.

    Returns:
        Default runtime job handlers keyed by job type.
    """

    return {
        "agent_inference": agent_worker.handle_agent_inference_job,
        "backtest": backtest_worker.handle_backtest_job,
        "experiment_run": backtest_worker.handle_backtest_job,
        "report_generation": report_worker.handle_report_generation_job,
        "rl_training": rl_worker.handle_training_job,
    }


def process_worker_jobs(
    service: RuntimeService,
    definition: WorkerDefinition,
    handlers: Mapping[JobType, JobHandler] | None = None,
    max_jobs: int = 1,
    on_job_finished: JobFinishedHandler | None = None,
) -> WorkerExecutionResult:
    """Process queued jobs supported by one worker definition.

    Args:
        service: Runtime service containing queued jobs.
        definition: Worker role definition.
        handlers: Optional handlers keyed by runtime job type.
        max_jobs: Maximum jobs to claim during this execution pass.
        on_job_finished: Optional callback receiving completed or failed jobs.

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
    callback_error_job_ids: list[UUID] = []
    callback_error_messages: list[str] = []

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
            _notify_job_finished(
                on_job_finished,
                failed_job,
                callback_error_job_ids,
                callback_error_messages,
            )
            continue
        try:
            result = handler(job)
        except Exception as error:
            failed_job = service.fail_job(job.job_id, str(error))
            failed_job_ids.append(failed_job.job_id)
            _notify_job_finished(
                on_job_finished,
                failed_job,
                callback_error_job_ids,
                callback_error_messages,
            )
        else:
            completed_job = service.complete_job(job.job_id, result)
            completed_job_ids.append(completed_job.job_id)
            _notify_job_finished(
                on_job_finished,
                completed_job,
                callback_error_job_ids,
                callback_error_messages,
            )

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
        callback_error_job_ids=tuple(callback_error_job_ids),
        callback_error_messages=tuple(callback_error_messages),
    )


def _notify_job_finished(
    handler: JobFinishedHandler | None,
    job: BackgroundJob,
    callback_error_job_ids: list[UUID],
    callback_error_messages: list[str],
) -> None:
    """Notify a finished-job hook and record callback failures.

    Args:
        handler: Optional finished-job callback.
        job: Completed or failed runtime job.
        callback_error_job_ids: Mutable callback error job ID accumulator.
        callback_error_messages: Mutable callback error message accumulator.
    """

    if handler is None:
        return
    try:
        handler(job)
    except Exception as error:
        callback_error_job_ids.append(job.job_id)
        callback_error_messages.append(str(error))


def run_worker_loop(
    service: RuntimeService,
    definitions: Sequence[WorkerDefinition] | None = None,
    handlers: Mapping[JobType, JobHandler] | None = None,
    max_jobs_per_tick: int = 1,
    interval_seconds: float = 2.0,
    max_iterations: int | None = None,
    sleep: Callable[[float], None] = time.sleep,
    on_job_finished: JobFinishedHandler | None = None,
    on_results: Callable[[tuple[WorkerExecutionResult, ...]], None] | None = None,
) -> tuple[tuple[WorkerExecutionResult, ...], ...]:
    """Run worker job processing until stopped.

    Args:
        service: Runtime service containing queued jobs.
        definitions: Optional worker definitions. All known definitions are used
            when omitted.
        handlers: Optional handlers keyed by runtime job type.
        max_jobs_per_tick: Maximum jobs each worker role may claim per tick.
        interval_seconds: Delay between worker polling ticks.
        max_iterations: Optional upper bound for tests.
        sleep: Sleep function used between ticks.
        on_job_finished: Optional callback receiving completed or failed jobs.
        on_results: Optional callback receiving each tick's execution results.

    Returns:
        Worker execution results for bounded runs.

    Raises:
        ValueError: If loop settings are invalid.
    """

    if max_jobs_per_tick < 1:
        raise ValueError("max_jobs_per_tick must be at least one.")
    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be greater than zero.")
    if max_iterations is not None and max_iterations < 1:
        raise ValueError("max_iterations must be at least one when provided.")

    worker_definitions = (
        tuple(definitions) if definitions is not None else build_worker_definitions()
    )
    collected_results: list[tuple[WorkerExecutionResult, ...]] = []
    iteration = 0
    while max_iterations is None or iteration < max_iterations:
        tick_results = tuple(
            process_worker_jobs(
                service=service,
                definition=definition,
                handlers=handlers,
                max_jobs=max_jobs_per_tick,
                on_job_finished=on_job_finished,
            )
            for definition in worker_definitions
        )
        if on_results is not None:
            on_results(tick_results)
        if max_iterations is not None:
            collected_results.append(tick_results)
        iteration += 1
        if max_iterations is None or iteration < max_iterations:
            sleep(interval_seconds)
    return tuple(collected_results)


def format_worker_execution_result(result: WorkerExecutionResult) -> dict[str, object]:
    """Format one worker execution result as JSON-serializable data.

    Args:
        result: Worker execution result.

    Returns:
        JSON-serializable result payload.
    """

    return {
        "worker_name": result.worker_name,
        "claimed_job_ids": [str(job_id) for job_id in result.claimed_job_ids],
        "completed_job_ids": [str(job_id) for job_id in result.completed_job_ids],
        "failed_job_ids": [str(job_id) for job_id in result.failed_job_ids],
        "remaining_queue_depth": result.remaining_queue_depth,
        "callback_error_job_ids": [
            str(job_id) for job_id in result.callback_error_job_ids
        ],
        "callback_error_messages": list(result.callback_error_messages),
    }


def main() -> int:
    """Run the worker loop and print JSON execution results.

    Returns:
        Process exit code.
    """

    settings = get_settings()

    def print_results(results: tuple[WorkerExecutionResult, ...]) -> None:
        """Print one worker tick result as JSON.

        Args:
            results: Worker execution results from one polling tick.
        """

        payload = [format_worker_execution_result(result) for result in results]
        print(json.dumps(payload, sort_keys=True), flush=True)

    try:
        run_worker_loop(
            service=get_runtime_service(),
            max_jobs_per_tick=settings.worker_max_jobs_per_tick,
            interval_seconds=settings.worker_poll_interval_seconds,
            on_results=print_results,
        )
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
