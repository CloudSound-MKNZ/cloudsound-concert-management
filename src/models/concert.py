"""Concert model for concert management service."""
from sqlalchemy import Column, String, DateTime, Integer, UniqueConstraint
from sqlalchemy.orm import relationship
from cloudsound_shared.models.base import Base, UUIDMixin, TimestampMixin
from cloudsound_shared.multitenancy import TenantMixin


class Concert(Base, UUIDMixin, TimestampMixin, TenantMixin):
    """Concert model representing a music concert event with tenant isolation."""
    
    __tablename__ = "concerts"
    
    date = Column(DateTime(timezone=True), nullable=False, index=True)
    location = Column(String(255), nullable=False)
    description = Column(String(2000), nullable=True)
    facebook_event_id = Column(String(255), nullable=True, index=True)  # Unique per tenant
    version = Column(Integer, nullable=False, default=1)  # Optimistic locking
    
    # Unique facebook_event_id within tenant
    __table_args__ = (
        UniqueConstraint('tenant_id', 'facebook_event_id', name='uq_concerts_tenant_facebook_event'),
    )
    
    # Relationships
    concert_artists = relationship("ConcertArtist", back_populates="concert", cascade="all, delete-orphan")
    
    def __repr__(self) -> str:
        return f"<Concert(id={self.id}, date='{self.date}', location='{self.location}', tenant_id={self.tenant_id})>"

