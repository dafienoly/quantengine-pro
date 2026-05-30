"""
QuantEngine Pro - Event Bus
=============================
Event-driven message dispatcher for the backtest engine.

Events flow: MARKET_DATA → SIGNAL → ORDER → FILL → POSITION_UPDATE

Handlers register for specific event types. When an event is published,
all matching handlers are called in registration order.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from loguru import logger


class EventType(str, Enum):
    """Types of events in the backtest system."""
    MARKET_DATA = "MARKET_DATA"       # New bar/tick available
    SIGNAL = "SIGNAL"                 # Strategy generated a signal
    ORDER_SUBMITTED = "ORDER_SUBMITTED"  # Order sent to broker
    ORDER_FILLED = "ORDER_FILLED"     # Order executed
    ORDER_CANCELLED = "ORDER_CANCELLED"  # Order cancelled
    ORDER_REJECTED = "ORDER_REJECTED"  # Order rejected (risk/margin)
    POSITION_UPDATE = "POSITION_UPDATE"  # Position changed
    PORTFOLIO_UPDATE = "PORTFOLIO_UPDATE"  # Portfolio value changed
    BAR_CLOSE = "BAR_CLOSE"           # Bar period ended (for daily settlement)
    BACKTEST_START = "BACKTEST_START"  # Backtest initialized
    BACKTEST_END = "BACKTEST_END"     # Backtest completed
    RISK_VIOLATION = "RISK_VIOLATION"  # Risk limit breached
    MARGIN_CALL = "MARGIN_CALL"       # Margin call triggered


@dataclass
class Event:
    """
    An event in the backtest system.

    Attributes:
        type: Event type
        timestamp: When the event occurred
        data: Event payload (type depends on event type)
        source: Which component generated this event
        metadata: Additional context
    """
    type: EventType
    timestamp: datetime
    data: Any = None
    source: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


# Type alias for event handler functions
EventHandler = Callable[[Event], None]


class EventBus:
    """
    Central event dispatcher for the backtest engine.

    Components publish events and subscribe to event types they're interested in.
    Events are processed synchronously in registration order (deterministic).

    Usage:
        bus = EventBus()
        bus.subscribe(EventType.MARKET_DATA, my_handler)
        bus.publish(Event(EventType.MARKET_DATA, now, bar_data))
    """

    def __init__(self):
        """Initialize empty event bus."""
        self._handlers: Dict[EventType, List[EventHandler]] = defaultdict(list)
        self._event_count: Dict[EventType, int] = defaultdict(int)
        self._event_log: List[Event] = []  # Full event history for debugging
        self._max_log_size = 100000  # Cap event log to avoid memory issues
        logger.info("EventBus initialized")

    def subscribe(self, event_type: EventType, handler: EventHandler) -> None:
        """
        Register a handler for a specific event type.

        Handlers are called in registration order when an event is published.

        Args:
            event_type: Type of event to listen for
            handler: Callable that takes an Event and returns None
        """
        self._handlers[event_type].append(handler)
        logger.debug(
            f"Subscribed {handler.__name__} to {event_type.value}"
        )

    def unsubscribe(self, event_type: EventType, handler: EventHandler) -> None:
        """
        Remove a handler registration.

        Args:
            event_type: Event type to unsubscribe from
            handler: Previously registered handler
        """
        if handler in self._handlers[event_type]:
            self._handlers[event_type].remove(handler)
            logger.debug(f"Unsubscribed {handler.__name__} from {event_type.value}")

    def publish(self, event: Event) -> None:
        """
        Publish an event to all registered handlers.

        Handlers are called synchronously in order. If a handler raises
        an exception, it is logged and subsequent handlers still run.

        Args:
            event: Event to publish
        """
        self._event_count[event.type] += 1

        # Store in event log (with size cap)
        if len(self._event_log) < self._max_log_size:
            self._event_log.append(event)

        handlers = self._handlers.get(event.type, [])
        for handler in handlers:
            try:
                handler(event)
            except Exception as e:
                logger.error(
                    f"Handler {handler.__name__} failed for {event.type.value}: {e}"
                )

    def publish_batch(self, events: List[Event]) -> None:
        """
        Publish multiple events in sequence.

        Args:
            events: List of events to publish in order
        """
        for event in events:
            self.publish(event)

    def clear_handlers(self, event_type: Optional[EventType] = None) -> None:
        """
        Clear registered handlers.

        Args:
            event_type: Specific type to clear, or None to clear all
        """
        if event_type:
            self._handlers[event_type].clear()
        else:
            self._handlers.clear()

    def get_event_log(
        self,
        event_type: Optional[EventType] = None,
        limit: int = 100,
    ) -> List[Event]:
        """
        Get recent events from the log.

        Args:
            event_type: Filter by event type (None = all)
            limit: Max events to return

        Returns:
            List of recent events
        """
        if event_type:
            filtered = [e for e in self._event_log if e.type == event_type]
            return filtered[-limit:]
        return self._event_log[-limit:]

    @property
    def stats(self) -> Dict:
        """Get event bus statistics."""
        return {
            "total_events": sum(self._event_count.values()),
            "by_type": dict(self._event_count),
            "handler_count": {
                et.value: len(handlers)
                for et, handlers in self._handlers.items()
            },
        }
