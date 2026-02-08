from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
import uuid


class PaperCatalogResponse(BaseModel):
    """Response model for paper catalog entries."""
    id: uuid.UUID
    title: str
    author: str
    abstract_text: Optional[str] = None
    status: Optional[str] = None
    created_at: Optional[datetime] = None
    synced_at: Optional[datetime] = None
    source: str = Field(default="local_db", description="Source of the data")


class PaperCreatedEvent(BaseModel):
    """Kafka event model for paper creation."""
    id: str
    title: str
    author: str
    abstractText: Optional[str] = None
    status: Optional[str] = "SUBMITTED"
    createdAt: Optional[str] = None
