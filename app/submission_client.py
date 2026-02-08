import httpx
import logging
from typing import Optional
from app.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError

logger = logging.getLogger(__name__)


class SubmissionClient:
    """Client for calling Submission Service with circuit breaker protection."""
    
    def __init__(self, base_url: str, circuit_breaker: CircuitBreaker):
        self.base_url = base_url.rstrip("/")
        self.circuit_breaker = circuit_breaker
        self.client = httpx.AsyncClient(timeout=5.0)
    
    async def get_paper(self, paper_id: str) -> Optional[dict]:
        """Fetch paper details from Submission Service with circuit breaker and fallback."""
        try:
            result = await self.circuit_breaker.call(self._fetch_paper, paper_id)
            return result
        except CircuitBreakerOpenError:
            logger.warning("Circuit breaker is OPEN, returning fallback")
            return None
        except Exception as e:
            logger.error(f"Failed to fetch paper from submission service: {e}")
            return None
    
    async def _fetch_paper(self, paper_id: str) -> Optional[dict]:
        """Internal method to fetch paper from Submission Service.
        
        Returns paper dict on success, None on 404.
        Raises on 5xx / connection errors so circuit breaker counts them as failures.
        """
        resp = await self.client.get(f"{self.base_url}/api/internal/papers/{paper_id}")
        
        if resp.status_code == 404:
            # 404 means the service is healthy, just the resource doesn't exist.
            # This should NOT count as a circuit breaker failure.
            return None
        
        # For 5xx or other unexpected errors, raise to trigger CB failure counting
        resp.raise_for_status()
        return resp.json()
    
    async def close(self) -> None:
        """Close HTTP client."""
        await self.client.aclose()
