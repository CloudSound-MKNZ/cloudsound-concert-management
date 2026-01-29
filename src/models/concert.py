"""Concert model for concert management service."""
from sqlalchemy import Column, String, DateTime, Integer, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
from cloudsound_shared.models.base import Base, UUIDMixin, TimestampMixin


class Concert(Base, UUIDMixin, TimestampMixin):
    """Concert model representing a music concert event."""
    
    __tablename__ = "concerts"
    
    date = Column(DateTime(timezone=True), nullable=False, index=True)
    location = Column(String(255), nullable=False)
    description = Column(String(2000), nullable=True)
    facebook_event_id = Column(String(255), nullable=True, unique=True, index=True)
    version = Column(Integer, nullable=False, default=1)  # Optimistic locking
    
    # Relationships
    concert_artists = relationship("ConcertArtist", back_populates="concert", cascade="all, delete-orphan")
    
    def __repr__(self) -> str:
        return f"<Concert(id={self.id}, date='{self.date}', location='{self.location}')>"

