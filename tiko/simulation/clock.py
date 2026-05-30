"""Simulation clock helpers."""

from datetime import datetime, timedelta


def advance_simulated_time(current_time: datetime, step_seconds: int) -> datetime:
    """Advance simulated time by a deterministic number of seconds.

    Args:
        current_time: Current simulated timestamp.
        step_seconds: Positive number of seconds to advance.

    Returns:
        Advanced simulated timestamp.

    Raises:
        ValueError: If the step is not positive.
    """

    if step_seconds <= 0:
        raise ValueError("Simulation step seconds must be positive.")
    return current_time + timedelta(seconds=step_seconds)
