"""Temporal decay functions.

Calculates time-based decay factors for storm events. Older events
contribute less to lead zone scores as roof damage is likely already repaired.
"""

import math
from datetime import datetime, timedelta, timezone
from typing import Any


# Constants
DECAY_RATE = 0.25
MAX_AGE_DAYS = 14


def calculate_decay(
    event_timestamp: datetime, current_time: datetime | None = None
) -> float:
    """Calculate temporal decay factor for a storm event.

    Uses exponential decay formula: e^(-0.25 * hours / 24)

    Args:
        event_timestamp: When the storm event occurred
        current_time: Reference time for decay calculation (defaults to UTC now)

    Returns:
        Decay factor between 0.0 and 1.0:
        - 1.0: Recent event (0 hours) or future event
        - 0.0: Event older than 14 days (fully decayed)
        - Between 0-1: Exponential decay based on age

    Examples:
        >>> from datetime import datetime, timedelta
        >>> now = datetime(2024, 1, 15, 12, 0, 0)
        >>> event = datetime(2024, 1, 15, 12, 0, 0)
        >>> calculate_decay(event, now)
        1.0
        >>> event_1d_ago = now - timedelta(days=1)
        >>> abs(calculate_decay(event_1d_ago, now) - 0.7788) < 0.001
        True
    """
    if current_time is None:
        current_time = datetime.now(timezone.utc)

    # Normalize to timezone-aware UTC for consistent comparison
    if event_timestamp.tzinfo is None:
        event_timestamp = event_timestamp.replace(tzinfo=timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)

    # Calculate time difference
    time_delta = current_time - event_timestamp
    hours_elapsed = time_delta.total_seconds() / 3600

    # Future events get no decay
    if hours_elapsed <= 0:
        return 1.0

    # Events older than MAX_AGE_DAYS are fully decayed
    max_hours = MAX_AGE_DAYS * 24
    if hours_elapsed >= max_hours:
        return 0.0

    # Apply exponential decay formula
    decay_factor = math.exp(-DECAY_RATE * hours_elapsed / 24)
    return decay_factor


def batch_decay(
    events_with_timestamps: list[tuple[Any, datetime]],
    current_time: datetime | None = None,
) -> list[tuple[Any, float]]:
    """Apply decay calculation to a batch of events.

    Useful for scoring engine to process multiple events efficiently.

    Args:
        events_with_timestamps: List of (item, timestamp) pairs
        current_time: Reference time for decay calculation (defaults to UTC now)

    Returns:
        List of (item, decay_factor) pairs in same order as input

    Examples:
        >>> from datetime import datetime, timedelta
        >>> now = datetime(2024, 1, 15, 12, 0, 0)
        >>> events = [
        ...     ("event1", now),
        ...     ("event2", now - timedelta(days=1)),
        ...     ("event3", now - timedelta(days=15)),
        ... ]
        >>> results = batch_decay(events, now)
        >>> results[0][1]  # Recent event
        1.0
        >>> results[2][1]  # Old event (>14 days)
        0.0
    """
    if current_time is None:
        current_time = datetime.now(timezone.utc)

    return [
        (item, calculate_decay(timestamp, current_time))
        for item, timestamp in events_with_timestamps
    ]
