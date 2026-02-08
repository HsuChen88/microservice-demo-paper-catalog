import asyncio
import json
import logging
import uuid
from datetime import datetime
from aiokafka import AIOKafkaConsumer
from aiokafka.errors import KafkaError
import asyncpg
from app.config import Settings
from app.metrics import KAFKA_EVENTS_CONSUMED

logger = logging.getLogger(__name__)


async def start_consumer(pool: asyncpg.Pool, settings: Settings) -> None:
    """Background task: consume paper-events topic and write to catalog DB."""
    consumer = AIOKafkaConsumer(
        settings.kafka_topic,
        bootstrap_servers=settings.kafka_bootstrap,
        group_id=settings.kafka_group_id,
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        auto_offset_reset="earliest",
    )
    
    # Retry connection loop
    while True:
        try:
            await consumer.start()
            logger.info(f"Kafka consumer started for topic: {settings.kafka_topic}")
            break
        except Exception as e:
            logger.warning(f"Kafka not ready ({e}), retrying in 5s...")
            await asyncio.sleep(5)
    
    try:
        async for msg in consumer:
            try:
                event = msg.value
                await upsert_paper(pool, event)
                KAFKA_EVENTS_CONSUMED.labels(status="success").inc()
                logger.info(f"Synced paper {event.get('id')} to catalog DB")
            except Exception as e:
                KAFKA_EVENTS_CONSUMED.labels(status="error").inc()
                logger.error(f"Error processing event: {e}", exc_info=True)
    except asyncio.CancelledError:
        logger.info("Kafka consumer task cancelled")
    except Exception as e:
        logger.error(f"Kafka consumer error: {e}", exc_info=True)
    finally:
        try:
            await consumer.stop()
            logger.info("Kafka consumer stopped")
        except Exception as e:
            logger.error(f"Error stopping Kafka consumer: {e}")


async def upsert_paper(pool: asyncpg.Pool, event: dict) -> None:
    """Insert or update paper in catalog DB."""
    try:
        paper_id = uuid.UUID(event["id"])
        title = event["title"]
        author = event["author"]
        abstract_text = event.get("abstractText", "")
        status = event.get("status", "SUBMITTED")
        
        # Parse createdAt if available
        created_at = None
        if event.get("createdAt"):
            try:
                created_at = datetime.fromisoformat(event["createdAt"].replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                created_at = datetime.utcnow()
        else:
            created_at = datetime.utcnow()
        
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO catalog_papers (id, title, author, abstract_text, status, created_at)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (id) DO UPDATE SET
                    title = EXCLUDED.title,
                    author = EXCLUDED.author,
                    abstract_text = EXCLUDED.abstract_text,
                    status = EXCLUDED.status,
                    synced_at = CURRENT_TIMESTAMP
            """, paper_id, title, author, abstract_text, status, created_at)
    except Exception as e:
        logger.error(f"Error upserting paper: {e}", exc_info=True)
        raise
