"""Reinforcement learning worker process definition."""

from collections.abc import Sequence

from tiko.domain.market import Candle, MarketEvent
from tiko.domain.runtime import BackgroundJob
from tiko.domain.simulation import SimulationRun
from tiko.rl_lab import build_static_policy_model_card, train_static_policy
from tiko.services.artifacts import ModelArtifactStore
from tiko.workers.definitions import WorkerDefinition


def build_definition() -> WorkerDefinition:
    """Build the reinforcement learning worker definition.

    Returns:
        Reinforcement learning worker definition.
    """

    return WorkerDefinition(
        worker_name="rl-worker",
        job_types=("rl_training",),
        description="Runs reinforcement learning training jobs.",
    )


def handle_training_job(job: BackgroundJob) -> dict[str, object]:
    """Run deterministic advisory RL training for one runtime job.

    Args:
        job: Claimed RL training job.

    Returns:
        Structured training result metadata.

    Raises:
        ValueError: If the job type or payload is invalid.
    """

    if job.job_type != "rl_training":
        raise ValueError("RL worker can only handle rl_training jobs.")
    run = SimulationRun.model_validate(_require_mapping(job.payload, "run"))
    candles = [
        Candle.model_validate(item)
        for item in _require_mapping_sequence(job.payload, "candles")
    ]
    events = [
        MarketEvent.model_validate(item)
        for item in _optional_mapping_sequence(job.payload, "events")
    ]
    candidate_action_ids = _optional_int_sequence(job.payload, "candidate_action_ids")
    summary = train_static_policy(
        run=run,
        candles=candles,
        events=events,
        candidate_action_ids=candidate_action_ids,
    )
    model_card = build_static_policy_model_card(summary)
    artifact_payload: dict[str, object] = {
        "job_id": str(job.job_id),
        "resource_type": job.resource_type,
        "resource_id": job.resource_id,
        "summary": summary.model_dump(mode="json"),
        "model_card": model_card.model_dump(mode="json"),
    }
    artifact = ModelArtifactStore(
        _optional_artifact_root(job.payload)
    ).store_json_artifact(
        artifact_id=job.job_id,
        model_type="rl",
        algorithm=summary.algorithm,
        payload=artifact_payload,
    )
    return {
        "message": "RL worker completed deterministic static policy training.",
        "job_type": job.job_type,
        "resource_type": job.resource_type,
        "resource_id": job.resource_id,
        "algorithm": summary.algorithm,
        "best_action_id": summary.best_action_id,
        "best_total_reward": str(summary.best_total_reward),
        "summary": summary.model_dump(mode="json"),
        "model_card": model_card.model_dump(mode="json"),
        "artifact": artifact.model_dump(mode="json"),
    }


def _require_mapping(
    payload: dict[str, object],
    key: str,
) -> dict[str, object]:
    """Read a required mapping from a job payload.

    Args:
        payload: Runtime job payload.
        key: Required payload key.

    Returns:
        Mapping value.

    Raises:
        ValueError: If the value is missing or not a mapping.
    """

    value = payload.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"RL training payload field {key} must be an object.")
    return value


def _require_mapping_sequence(
    payload: dict[str, object],
    key: str,
) -> tuple[dict[str, object], ...]:
    """Read a required sequence of mappings from a job payload.

    Args:
        payload: Runtime job payload.
        key: Required payload key.

    Returns:
        Mapping values.

    Raises:
        ValueError: If the value is missing or not a sequence of mappings.
    """

    value = payload.get(key)
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError(f"RL training payload field {key} must be a list of objects.")
    return tuple(value)


def _optional_mapping_sequence(
    payload: dict[str, object],
    key: str,
) -> tuple[dict[str, object], ...]:
    """Read an optional sequence of mappings from a job payload.

    Args:
        payload: Runtime job payload.
        key: Optional payload key.

    Returns:
        Mapping values.

    Raises:
        ValueError: If the value is present but invalid.
    """

    if key not in payload:
        return ()
    return _require_mapping_sequence(payload, key)


def _optional_int_sequence(
    payload: dict[str, object],
    key: str,
) -> Sequence[int] | None:
    """Read an optional sequence of integer action IDs from a job payload.

    Args:
        payload: Runtime job payload.
        key: Optional payload key.

    Returns:
        Integer action IDs or `None` when absent.

    Raises:
        ValueError: If the value is present but invalid.
    """

    if key not in payload:
        return None
    value = payload[key]
    if not isinstance(value, list) or not all(
        isinstance(item, int) and not isinstance(item, bool) for item in value
    ):
        raise ValueError(f"RL training payload field {key} must be a list of integers.")
    return tuple(value)


def _optional_artifact_root(payload: dict[str, object]) -> str:
    """Read the optional artifact root from a job payload.

    Args:
        payload: Runtime job payload.

    Returns:
        Artifact root path string.

    Raises:
        ValueError: If the value is present but invalid.
    """

    value = payload.get("artifact_root", ".tiko/artifacts")
    if not isinstance(value, str) or not value:
        raise ValueError("RL training payload field artifact_root is invalid.")
    return value
