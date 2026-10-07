"""
Circuit Breaker — prevents cascading failures in scrapers.
States: CLOSED (normal) → OPEN (failing, skip) → HALF-OPEN (probe)
"""
import asyncio
import time
import logging
from enum import Enum
from typing import Callable, Any
from app.config.settings import CIRCUIT_BREAKER_THRESHOLD, CIRCUIT_BREAKER_RECOVERY_S, CIRCUIT_BREAKER_RECOVERY_ML_S

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "CLOSED"       # Normal operation
    OPEN = "OPEN"           # Failing — reject calls
    HALF_OPEN = "HALF_OPEN" # Testing recovery


class CircuitBreaker:
    def __init__(
        self,
        name: str,
        failure_threshold: int = 3,
        recovery_timeout: int = 60,
        success_threshold: int = 2,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: float = 0.0

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN:
            elapsed = time.monotonic() - self._last_failure_time
            if elapsed >= self.recovery_timeout:
                logger.info(f"[CB:{self.name}] Transitioning OPEN → HALF_OPEN after {elapsed:.0f}s")
                self._state = CircuitState.HALF_OPEN
                self._success_count = 0
        return self._state

    def reset(self):
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = 0.0

    def record_success(self):
        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self.success_threshold:
                logger.info(f"[CB:{self.name}] HALF_OPEN → CLOSED (recovered)")
                self._state = CircuitState.CLOSED
                self._failure_count = 0
        elif self._state == CircuitState.CLOSED:
            self._failure_count = max(0, self._failure_count - 1)

    def record_failure(self):
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        if self._failure_count >= self.failure_threshold:
            if self._state != CircuitState.OPEN:
                logger.warning(
                    f"[CB:{self.name}] CLOSED → OPEN after {self._failure_count} failures. "
                    f"Will retry in {self.recovery_timeout}s."
                )
            self._state = CircuitState.OPEN

    def is_open(self) -> bool:
        return self.state == CircuitState.OPEN

    async def call(self, func: Callable, *args, **kwargs) -> Any:
        if self.is_open():
            raise RuntimeError(f"CircuitBreaker [{self.name}] is OPEN — skipping call")
        try:
            result = await func(*args, **kwargs)
            self.record_success()
            return result
        except Exception as exc:
            self.record_failure()
            raise exc

    def status_dict(self) -> dict:
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self._failure_count,
            "seconds_since_last_failure": (
                round(time.monotonic() - self._last_failure_time, 1)
                if self._last_failure_time else None
            ),
        }


# Global registry — one breaker per marketplace
_breakers: dict[str, CircuitBreaker] = {}


def get_breaker(marketplace: str) -> CircuitBreaker:
    key = marketplace.lower().replace(" ", "_")
    recovery = CIRCUIT_BREAKER_RECOVERY_ML_S if key == "mercado_libre" else CIRCUIT_BREAKER_RECOVERY_S
    return _breakers.setdefault(key, CircuitBreaker(
        name=key, 
        failure_threshold=CIRCUIT_BREAKER_THRESHOLD, 
        recovery_timeout=recovery
    ))


def all_breaker_statuses() -> list[dict]:
    return [b.status_dict() for b in _breakers.values()]
