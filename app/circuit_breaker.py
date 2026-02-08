import asyncio
import logging
import time
from enum import Enum
from typing import Callable, Any

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is OPEN and request is rejected."""
    pass


class CircuitBreaker:
    """Simple async circuit breaker implementation."""
    
    def __init__(
        self,
        max_failures: int = 5,
        reset_timeout: float = 30.0,
        call_timeout: float = 5.0
    ):
        self.max_failures = max_failures
        self.reset_timeout = reset_timeout
        self.call_timeout = call_timeout
        self.failure_count = 0
        self.last_failure_time: float | None = None
        self.state = CircuitState.CLOSED
        self._lock = asyncio.Lock()
    
    async def call(self, func: Callable, *args: Any, **kwargs: Any) -> Any:
        """Execute function with circuit breaker protection."""
        async with self._lock:
            # Check if we should attempt reset
            if self.state == CircuitState.OPEN:
                if self._should_attempt_reset():
                    self.state = CircuitState.HALF_OPEN
                    logger.info("Circuit breaker transitioning to HALF_OPEN")
                else:
                    raise CircuitBreakerOpenError("Circuit breaker is OPEN")
        
        # Execute the function with timeout
        try:
            result = await asyncio.wait_for(
                func(*args, **kwargs),
                timeout=self.call_timeout
            )
            await self._record_success()
            return result
        except asyncio.TimeoutError:
            logger.warning(f"Function call timed out after {self.call_timeout}s")
            await self._record_failure()
            raise
        except Exception as e:
            logger.error(f"Function call failed: {e}")
            await self._record_failure()
            raise
    
    async def _record_failure(self) -> None:
        """Record a failure and update circuit breaker state."""
        async with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()
            
            if self.state == CircuitState.HALF_OPEN:
                # Half-open failed, go back to OPEN
                self.state = CircuitState.OPEN
                logger.warning("Circuit breaker transitioning to OPEN (half-open test failed)")
            elif self.state == CircuitState.CLOSED:
                if self.failure_count >= self.max_failures:
                    self.state = CircuitState.OPEN
                    logger.warning(f"Circuit breaker transitioning to OPEN (failures: {self.failure_count})")
    
    async def _record_success(self) -> None:
        """Record a success and update circuit breaker state."""
        async with self._lock:
            self.failure_count = 0
            self.last_failure_time = None
            
            if self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.CLOSED
                logger.info("Circuit breaker transitioning to CLOSED (half-open test succeeded)")
    
    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset."""
        if self.last_failure_time is None:
            return True
        return (time.time() - self.last_failure_time) >= self.reset_timeout
    
    def get_state(self) -> CircuitState:
        """Get current circuit breaker state."""
        return self.state
