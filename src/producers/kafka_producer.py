"""Kafka producer for concert events.

Publishes concert creation and update events to Kafka for downstream processing
by the music-discovery service.
"""
from typing import Optional, Dict, Any, List
from datetime import datetime
from uuid import UUID
import structlog

from cloudsound_shared.kafka import KafkaProducerClient
from cloudsound_shared.config.settings import app_settings

logger = structlog.get_logger(__name__)

# Topics
CONCERT_CREATED_TOPIC = "concerts.created"
CONCERT_UPDATED_TOPIC = "concerts.updated"

# Global producer instance
_producer: Optional["ConcertEventProducer"] = None


class ConcertEventProducer:
    """Kafka producer for concert event messages.
    
    Publishes events when concerts are created or updated:
    - concerts.created: Triggers music discovery to find and download tracks
    - concerts.updated: Updates to concert info (new artists, description changes)
    
    Usage:
        producer = ConcertEventProducer()
        producer.connect()
        
        producer.publish_concert_created(
            concert_id="uuid",
            location="Venue Name",
            description="Concert with music links...",
            artists=["Artist Name"],
        )
    """
    
    def __init__(
        self,
        client: Optional[KafkaProducerClient] = None,
    ):
        """Initialize concert event producer.
        
        Args:
            client: Optional pre-configured Kafka client
        """
        self._client = client
        self._connected = False
        
        logger.info("concert_event_producer_initialized")
    
    def connect(self) -> None:
        """Connect to Kafka."""
        if self._connected:
            return
        
        if not self._client:
            self._client = KafkaProducerClient(
                bootstrap_servers=app_settings.kafka_bootstrap_servers,
            )
        
        try:
            self._client.connect()
            self._connected = True
            logger.info("concert_event_producer_connected")
        except Exception as e:
            logger.error("concert_event_producer_connection_failed", error=str(e))
            raise
    
    def close(self) -> None:
        """Close connection."""
        if self._client:
            self._client.close()
            self._connected = False
            logger.info("concert_event_producer_closed")
    
    def is_connected(self) -> bool:
        """Check if producer is connected."""
        return self._connected
    
    def publish_concert_created(
        self,
        concert_id: UUID,
        location: str,
        date: datetime,
        description: Optional[str] = None,
        artists: Optional[List[str]] = None,
        facebook_event_id: Optional[str] = None,
    ) -> None:
        """Publish concert created event.
        
        This triggers the music-discovery service to:
        1. Extract music links from the description
        2. Search for artist tracks
        3. Queue downloads for found music
        
        Args:
            concert_id: Concert UUID
            location: Venue/location name
            date: Concert date
            description: Concert description (may contain music links)
            artists: List of artist names
            facebook_event_id: Source Facebook event ID if applicable
        """
        if not self._connected:
            self.connect()
        
        event = {
            "event_type": "concert.created",
            "concert_id": str(concert_id),
            "location": location,
            "date": date.isoformat() if hasattr(date, 'isoformat') else str(date),
            "description": description,
            "artists": artists or [],
            "facebook_event_id": facebook_event_id,
            "timestamp": datetime.utcnow().isoformat(),
        }
        
        self._client.send(
            CONCERT_CREATED_TOPIC,
            value=event,
            key=str(concert_id),
        )
        
        logger.info(
            "concert_created_event_published",
            concert_id=str(concert_id),
            location=location,
            artist_count=len(artists) if artists else 0,
        )
    
    def publish_concert_updated(
        self,
        concert_id: UUID,
        location: str,
        date: datetime,
        description: Optional[str] = None,
        artists: Optional[List[str]] = None,
        facebook_event_id: Optional[str] = None,
    ) -> None:
        """Publish concert updated event.
        
        Args:
            concert_id: Concert UUID
            location: Venue/location name
            date: Concert date
            description: Concert description
            artists: List of artist names
            facebook_event_id: Source Facebook event ID if applicable
        """
        if not self._connected:
            self.connect()
        
        event = {
            "event_type": "concert.updated",
            "concert_id": str(concert_id),
            "location": location,
            "date": date.isoformat() if hasattr(date, 'isoformat') else str(date),
            "description": description,
            "artists": artists or [],
            "facebook_event_id": facebook_event_id,
            "timestamp": datetime.utcnow().isoformat(),
        }
        
        self._client.send(
            CONCERT_UPDATED_TOPIC,
            value=event,
            key=str(concert_id),
        )
        
        logger.info(
            "concert_updated_event_published",
            concert_id=str(concert_id),
            location=location,
        )
    
    def flush(self) -> None:
        """Flush pending messages."""
        if self._client and self._client.producer:
            self._client.producer.flush()


def get_concert_producer() -> ConcertEventProducer:
    """Get the global concert producer instance.
    
    Returns:
        ConcertEventProducer: The singleton producer instance
    """
    global _producer
    if _producer is None:
        _producer = ConcertEventProducer()
    return _producer


def initialize_producer() -> None:
    """Initialize and connect the global producer."""
    producer = get_concert_producer()
    producer.connect()


def shutdown_producer() -> None:
    """Shutdown the global producer."""
    global _producer
    if _producer:
        _producer.close()
        _producer = None

