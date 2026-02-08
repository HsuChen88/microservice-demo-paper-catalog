from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

# Request metrics
REQUEST_COUNT = Counter(
    "catalog_requests_total",
    "Total requests",
    ["method", "endpoint", "status"]
)

REQUEST_LATENCY = Histogram(
    "catalog_request_duration_seconds",
    "Request latency",
    ["method", "endpoint"]
)

# Kafka metrics
KAFKA_EVENTS_CONSUMED = Counter(
    "catalog_kafka_events_total",
    "Kafka events consumed",
    ["status"]
)

# Circuit breaker metrics
CIRCUIT_BREAKER_STATE = Gauge(
    "catalog_circuit_breaker_state",
    "Circuit breaker state (0=closed, 1=open, 2=half-open)"
)


def get_metrics_content():
    """Get Prometheus metrics content."""
    return generate_latest()
