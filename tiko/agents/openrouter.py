"""OpenRouter-backed structured trading agent."""

import json
from collections.abc import Callable
from decimal import Decimal
from json import JSONDecodeError
from typing import Literal, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from tiko.domain.decision import TradeIntent
from tiko.domain.observation import Observation

OPENROUTER_CHAT_COMPLETIONS_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_DEFAULT_MODEL = "openrouter/free"

TradeIntentAction = Literal[
    "open_long",
    "open_short",
    "increase_long",
    "increase_short",
    "reduce_long",
    "reduce_short",
    "close_position",
    "hold",
    "rebalance",
]
OpenRouterTransport = Callable[
    [str, dict[str, str], dict[str, object], int], dict[str, object]
]

TRADE_INTENT_PROPOSAL_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "action",
        "target_weight",
        "max_leverage",
        "confidence",
        "expected_holding_period",
        "thesis",
        "evidence",
        "invalidation_conditions",
        "data_quality_score",
    ],
    "properties": {
        "action": {
            "type": "string",
            "enum": [
                "open_long",
                "open_short",
                "increase_long",
                "increase_short",
                "reduce_long",
                "reduce_short",
                "close_position",
                "hold",
                "rebalance",
            ],
        },
        "target_weight": {"type": "string"},
        "target_notional": {"type": ["string", "null"]},
        "max_leverage": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "expected_holding_period": {"type": "string", "minLength": 1},
        "thesis": {"type": "string", "minLength": 1},
        "evidence": {
            "type": "array",
            "items": {"type": "object", "additionalProperties": True},
        },
        "invalidation_conditions": {
            "type": "array",
            "items": {"type": "string"},
        },
        "data_quality_score": {"type": "number", "minimum": 0, "maximum": 1},
    },
}


class OpenRouterAgentError(ValueError):
    """Raised when OpenRouter agent evaluation cannot produce valid intent."""


class OpenRouterClient:
    """Call OpenRouter chat completions with structured output requests."""

    def __init__(
        self,
        api_key: str,
        model: str = OPENROUTER_DEFAULT_MODEL,
        endpoint: str = OPENROUTER_CHAT_COMPLETIONS_URL,
        timeout_seconds: int = 60,
        transport: OpenRouterTransport | None = None,
        allow_json_object_fallback: bool = True,
    ) -> None:
        """Initialize the OpenRouter client.

        Args:
            api_key: OpenRouter API key.
            model: OpenRouter model or router slug.
            endpoint: Chat completions endpoint.
            timeout_seconds: Request timeout in seconds.
            transport: Optional fake transport for tests.
            allow_json_object_fallback: Whether to retry with JSON mode when schema
                mode fails.
        """

        if not api_key:
            raise OpenRouterAgentError("OpenRouter API key is required.")
        self._api_key = api_key
        self._model = model
        self._endpoint = endpoint
        self._timeout_seconds = timeout_seconds
        self._transport = transport or self._default_transport
        self._allow_json_object_fallback = allow_json_object_fallback

    def create_structured_completion(
        self,
        messages: list[dict[str, str]],
        json_schema: dict[str, object],
    ) -> dict[str, object]:
        """Create one schema-constrained chat completion.

        Args:
            messages: Chat messages for the provider.
            json_schema: JSON Schema enforced through OpenRouter response format.

        Returns:
            Parsed JSON object from the assistant message.

        Raises:
            OpenRouterAgentError: If the response is invalid or unavailable.
        """

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "X-OpenRouter-Title": "Tiko Simulation Agent",
        }
        response_formats = [self._json_schema_response_format(json_schema)]
        if self._allow_json_object_fallback:
            response_formats.append({"type": "json_object"})
        first_error: OpenRouterAgentError | None = None
        for response_format in response_formats:
            try:
                response = self._transport(
                    self._endpoint,
                    headers,
                    self._build_payload(messages, response_format),
                    self._timeout_seconds,
                )
                return self._extract_json_content(response)
            except OpenRouterAgentError as error:
                if first_error is None:
                    first_error = error
        if first_error is not None:
            raise first_error
        raise OpenRouterAgentError("OpenRouter response format list was empty.")

    def _build_payload(
        self,
        messages: list[dict[str, str]],
        response_format: dict[str, object],
    ) -> dict[str, object]:
        """Build a chat completion request payload.

        Args:
            messages: Chat messages for the provider.
            response_format: OpenRouter response format.

        Returns:
            Request payload.
        """

        return {
            "model": self._model,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 2000,
            "response_format": response_format,
        }

    def _json_schema_response_format(
        self, json_schema: dict[str, object]
    ) -> dict[str, object]:
        """Build the strict JSON Schema response format.

        Args:
            json_schema: JSON Schema enforced through OpenRouter response format.

        Returns:
            OpenRouter response format.
        """

        return {
            "type": "json_schema",
            "json_schema": {
                "name": "trade_intent_proposal",
                "strict": True,
                "schema": json_schema,
            },
        }

    def _default_transport(
        self,
        endpoint: str,
        headers: dict[str, str],
        payload: dict[str, object],
        timeout_seconds: int,
    ) -> dict[str, object]:
        """Send one HTTP request to OpenRouter.

        Args:
            endpoint: Chat completions endpoint.
            headers: HTTP headers.
            payload: JSON request body.
            timeout_seconds: Request timeout in seconds.

        Returns:
            Decoded JSON response.

        Raises:
            OpenRouterAgentError: If the HTTP request or JSON decoding fails.
        """

        request = Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                response_body = response.read().decode("utf-8")
        except HTTPError as error:
            details = error.read().decode("utf-8", errors="replace")
            raise OpenRouterAgentError(
                "OpenRouter request failed with HTTP "
                f"{error.code}: {self._extract_error_message(details)}"
            ) from error
        except URLError as error:
            raise OpenRouterAgentError(f"OpenRouter request failed: {error}") from error
        try:
            decoded = json.loads(response_body)
        except JSONDecodeError as error:
            raise OpenRouterAgentError("OpenRouter returned invalid JSON.") from error
        if not isinstance(decoded, dict):
            raise OpenRouterAgentError("OpenRouter response must be a JSON object.")
        return decoded

    def _extract_error_message(self, response_body: str) -> str:
        """Extract a safe provider error message from an HTTP response body.

        Args:
            response_body: Provider response body.

        Returns:
            Error message without provider metadata.
        """

        try:
            decoded = json.loads(response_body)
        except JSONDecodeError:
            return "provider returned an error"
        if not isinstance(decoded, dict):
            return "provider returned an error"
        error = decoded.get("error")
        if not isinstance(error, dict):
            return "provider returned an error"
        message = error.get("message")
        if not isinstance(message, str) or not message:
            return "provider returned an error"
        return message

    def _extract_json_content(self, response: dict[str, object]) -> dict[str, object]:
        """Extract parsed assistant JSON from a chat completion response.

        Args:
            response: OpenRouter chat completion response.

        Returns:
            Parsed assistant content.

        Raises:
            OpenRouterAgentError: If content cannot be parsed as a JSON object.
        """

        provider_error = response.get("error")
        if isinstance(provider_error, dict):
            message = provider_error.get("message", "unknown provider error")
            raise OpenRouterAgentError(f"OpenRouter error: {message}")
        choices = response.get("choices")
        if not isinstance(choices, list) or not choices:
            raise OpenRouterAgentError("OpenRouter response did not include choices.")
        first_choice = choices[0]
        if not isinstance(first_choice, dict):
            raise OpenRouterAgentError("OpenRouter choice must be a JSON object.")
        message = first_choice.get("message")
        if not isinstance(message, dict):
            raise OpenRouterAgentError("OpenRouter choice did not include a message.")
        content = message.get("content")
        if isinstance(content, dict):
            return cast(dict[str, object], content)
        if not isinstance(content, str) or not content.strip():
            raise OpenRouterAgentError("OpenRouter message content is empty.")
        try:
            proposal = json.loads(content)
        except JSONDecodeError as error:
            raise OpenRouterAgentError(
                "OpenRouter message content is not valid JSON."
            ) from error
        if not isinstance(proposal, dict):
            raise OpenRouterAgentError(
                "OpenRouter message content must be a JSON object."
            )
        return cast(dict[str, object], proposal)


class OpenRouterTraderAgent:
    """Create structured simulated intent through OpenRouter inference."""

    def __init__(
        self,
        client: OpenRouterClient,
        agent_id: str = "openrouter_trader",
    ) -> None:
        """Initialize the OpenRouter-backed trader agent.

        Args:
            client: OpenRouter client.
            agent_id: Stable agent identifier.
        """

        self.agent_id = agent_id
        self._client = client

    def decide(self, observation: Observation) -> TradeIntent:
        """Create structured trade intent from an observation.

        Args:
            observation: Point-in-time-safe observation.

        Returns:
            Structured trade intent.
        """

        proposal = self._client.create_structured_completion(
            messages=self._build_messages(observation),
            json_schema=TRADE_INTENT_PROPOSAL_SCHEMA,
        )
        return self._build_intent(observation, proposal)

    def _build_messages(self, observation: Observation) -> list[dict[str, str]]:
        """Build OpenRouter chat messages for one observation.

        Args:
            observation: Point-in-time-safe observation.

        Returns:
            Chat messages.
        """

        return [
            {
                "role": "system",
                "content": (
                    "You are a simulation-only crypto research agent. "
                    "You never place orders, request private account data, "
                    "or bypass risk review. Return only JSON that matches "
                    "the requested schema. Keep text fields concise."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    self._build_observation_payload(observation),
                    sort_keys=True,
                ),
            },
        ]

    def _build_observation_payload(self, observation: Observation) -> dict[str, object]:
        """Build a compact provider payload from an observation.

        Args:
            observation: Point-in-time-safe observation.

        Returns:
            JSON-serializable observation payload.
        """

        return {
            "task": "Propose one simulated trade intent.",
            "simulation_only": True,
            "run_id": str(observation.run_id),
            "symbol": observation.symbol,
            "as_of": observation.as_of.isoformat(),
            "account": {
                "base_currency": observation.account.base_currency,
                "cash_balance": str(observation.account.cash_balance),
                "total_equity": str(observation.account.total_equity),
                "max_drawdown": str(observation.account.max_drawdown),
            },
            "candles": [
                candle.model_dump(mode="json") for candle in observation.candles[-20:]
            ],
            "events": [
                event.model_dump(mode="json") for event in observation.events[-20:]
            ],
        }

    def _build_intent(
        self, observation: Observation, proposal: dict[str, object]
    ) -> TradeIntent:
        """Convert a provider proposal into an observation-scoped intent.

        Args:
            observation: Source observation.
            proposal: Provider proposal fields.

        Returns:
            Validated trade intent.
        """

        target_notional_value = proposal.get("target_notional")
        target_notional = (
            Decimal(str(target_notional_value))
            if target_notional_value is not None
            else None
        )
        return TradeIntent(
            decision_id=uuid4(),
            run_id=observation.run_id,
            agent_id=self.agent_id,
            symbol=observation.symbol,
            market_type="synthetic",
            action=cast(TradeIntentAction, self._require_string(proposal, "action")),
            target_weight=Decimal(str(proposal["target_weight"])),
            target_notional=target_notional,
            max_leverage=Decimal(str(proposal["max_leverage"])),
            confidence=self._require_float(proposal, "confidence"),
            expected_holding_period=self._require_string(
                proposal, "expected_holding_period"
            ),
            thesis=self._require_string(proposal, "thesis"),
            evidence=self._require_evidence(proposal),
            invalidation_conditions=self._require_string_list(
                proposal, "invalidation_conditions"
            ),
            data_quality_score=self._require_float(proposal, "data_quality_score"),
            created_at_sim_time=observation.as_of,
        )

    def _require_string(self, proposal: dict[str, object], key: str) -> str:
        """Read a required string proposal field.

        Args:
            proposal: Provider proposal fields.
            key: Field key.

        Returns:
            Field value.

        Raises:
            OpenRouterAgentError: If the field is missing or not a string.
        """

        value = proposal.get(key)
        if not isinstance(value, str):
            raise OpenRouterAgentError(f"OpenRouter proposal field {key} is invalid.")
        return value

    def _require_string_list(self, proposal: dict[str, object], key: str) -> list[str]:
        """Read a required string-list proposal field.

        Args:
            proposal: Provider proposal fields.
            key: Field key.

        Returns:
            Field values.

        Raises:
            OpenRouterAgentError: If the field is missing or invalid.
        """

        value = proposal.get(key)
        if not isinstance(value, list) or not all(
            isinstance(item, str) for item in value
        ):
            raise OpenRouterAgentError(f"OpenRouter proposal field {key} is invalid.")
        return value

    def _require_float(self, proposal: dict[str, object], key: str) -> float:
        """Read a required numeric proposal field.

        Args:
            proposal: Provider proposal fields.
            key: Field key.

        Returns:
            Numeric field value.

        Raises:
            OpenRouterAgentError: If the field is missing or invalid.
        """

        value = proposal.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            raise OpenRouterAgentError(f"OpenRouter proposal field {key} is invalid.")
        return float(value)

    def _require_evidence(self, proposal: dict[str, object]) -> list[dict[str, object]]:
        """Read required structured evidence.

        Args:
            proposal: Provider proposal fields.

        Returns:
            Evidence objects.

        Raises:
            OpenRouterAgentError: If evidence is missing or invalid.
        """

        value = proposal.get("evidence")
        if not isinstance(value, list) or not all(
            isinstance(item, dict) for item in value
        ):
            raise OpenRouterAgentError("OpenRouter proposal field evidence is invalid.")
        return [cast(dict[str, object], item) for item in value]
