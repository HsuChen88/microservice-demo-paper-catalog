from pydantic_settings import BaseSettings
from pydantic import ConfigDict


class Settings(BaseSettings):
    # Database
    db_host: str = "localhost"
    db_port: int = 5433  # Replica port
    db_name: str = "catalog_db"
    db_user: str = "postgres"
    db_password: str = "postgres"
    
    # Kafka
    kafka_bootstrap: str = "localhost:9092"
    kafka_topic: str = "paper-events"
    kafka_group_id: str = "catalog-consumer-group"
    
    # Submission Service (for service-to-service calls)
    submission_service_url: str = "http://localhost:8081"
    
    # Circuit breaker settings
    cb_max_failures: int = 5
    cb_reset_timeout: float = 30.0
    cb_call_timeout: float = 5.0

    model_config = ConfigDict(env_prefix="", env_file=".env")


_settings: Settings | None = None


def get_settings() -> Settings:
    """Get singleton settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
