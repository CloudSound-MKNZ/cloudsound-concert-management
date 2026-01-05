"""ConcertArtist junction model for concert management service."""
from sqlalchemy import Column, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from cloudsound_shared.models.base import Base, UUIDMixin, TimestampMixin


class ConcertArtist(Base, UUIDMixin, TimestampMixin):
    """Junction model linking concerts to artists."""
    
    __tablename__ = "concert_artists"
    
    concert_id = Column(UUID(as_uuid=True), ForeignKey("concerts.id", ondelete="CASCADE"), nullable=False, index=True)
    artist_id = Column(UUID(as_uuid=True), ForeignKey("artists.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Relationships
    concert = relationship("Concert", back_populates="concert_artists")
    # Note: Artist model is in radio-streaming service, relationship loaded via join in service layer
    
    def __repr__(self) -> str:
        return f"<ConcertArtist(id={self.id}, concert_id={self.concert_id}, artist_id={self.artist_id})>"

