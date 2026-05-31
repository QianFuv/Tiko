"""Agent inference worker process definition."""

from tiko.agents import (
    AgentRuntime,
    OpenRouterClient,
    OpenRouterTraderAgent,
    RuleBasedTraderAgent,
    TradingAgent,
)
from tiko.core.config import get_settings
from tiko.domain.observation import Observation
from tiko.domain.runtime import BackgroundJob
from tiko.workers.definitions import WorkerDefinition


def build_definition() -> WorkerDefinition:
    """Build the agent worker definition.

    Returns:
        Agent worker definition.
    """

    return WorkerDefinition(
        worker_name="agent-worker",
        job_types=("agent_inference",),
        description="Runs agent inference outside request handlers.",
    )


def handle_agent_inference_job(job: BackgroundJob) -> dict[str, object]:
    """Run structured agent inference for one runtime job.

    Args:
        job: Claimed agent inference job.

    Returns:
        Structured agent inference result metadata.

    Raises:
        ValueError: If the job type, payload, or agent configuration is invalid.
    """

    if job.job_type != "agent_inference":
        raise ValueError("Agent worker can only handle agent_inference jobs.")
    observation = Observation.model_validate(
        _require_mapping(job.payload, "observation")
    )
    agent_type = _read_agent_type(job.payload)
    agent = _build_agent(agent_type)
    intent = AgentRuntime(agent).evaluate(observation)
    return {
        "message": "Agent worker completed structured inference.",
        "job_type": job.job_type,
        "resource_type": job.resource_type,
        "resource_id": job.resource_id,
        "agent_type": agent_type,
        "agent_id": intent.agent_id,
        "observation_id": str(observation.observation_id),
        "run_id": str(observation.run_id),
        "symbol": observation.symbol,
        "intent": intent.model_dump(mode="json"),
    }


def _require_mapping(payload: dict[str, object], key: str) -> dict[str, object]:
    """Read a required mapping value from a job payload.

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
        raise ValueError(f"Agent inference payload field {key} must be an object.")
    return value


def _read_agent_type(payload: dict[str, object]) -> str:
    """Read and normalize the requested agent type.

    Args:
        payload: Runtime job payload.

    Returns:
        Normalized agent type.

    Raises:
        ValueError: If the agent type is invalid or unsupported.
    """

    value = payload.get("agent_type", "rule_based")
    if not isinstance(value, str) or not value:
        raise ValueError(
            "Agent inference payload field agent_type must be a non-empty string."
        )
    if value == "openrouter":
        return "llm_openrouter"
    if value in {"rule_based", "llm_openrouter"}:
        return value
    raise ValueError(f"Unsupported agent_type {value}.")


def _build_agent(agent_type: str) -> TradingAgent:
    """Build an agent implementation for the normalized agent type.

    Args:
        agent_type: Normalized agent type.

    Returns:
        Trading agent implementation.

    Raises:
        ValueError: If OpenRouter is requested without configuration.
    """

    if agent_type == "rule_based":
        return RuleBasedTraderAgent()
    settings = get_settings()
    if (
        settings.openrouter_api_key is None
        or not settings.openrouter_api_key.get_secret_value()
    ):
        raise ValueError("OpenRouter API key is not configured.")
    client = OpenRouterClient(
        api_key=settings.openrouter_api_key.get_secret_value(),
        model=settings.openrouter_model,
        endpoint=settings.openrouter_chat_endpoint,
        timeout_seconds=settings.openrouter_timeout_seconds,
    )
    return OpenRouterTraderAgent(client)
