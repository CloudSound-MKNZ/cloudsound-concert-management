"""Concert API endpoints."""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel
from cloudsound_shared.db.pool import get_db
from ..services.concert_service import ConcertService, ConcertConflictError
from ..models import Concert, ConcertArtist
from cloudsound_shared.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/concerts", tags=["concerts"])


class ArtistResponse(BaseModel):
    """Artist response model."""
    id: UUID
    name: str
    genre: Optional[str] = None
    
    class Config:
        from_attributes = True


class ConcertArtistResponse(BaseModel):
    """ConcertArtist response model."""
    id: UUID
    artist_id: UUID
    artist: Optional[ArtistResponse] = None
    
    class Config:
        from_attributes = True


class ConcertResponse(BaseModel):
    """Concert response model."""
    id: UUID
    date: str  # ISO format string
    location: str
    description: Optional[str] = None
    facebook_event_id: Optional[str] = None
    version: int
    created_at: str  # ISO format string
    updated_at: str  # ISO format string
    artists: List[ArtistResponse] = []
    
    class Config:
        from_attributes = True
    
    @classmethod
    def from_orm_with_artists(cls, concert: Concert) -> "ConcertResponse":
        """Create response from concert with artists loaded."""
        artists = [
            ArtistResponse(
                id=ca.artist.id,
                name=ca.artist.name,
                genre=ca.artist.genre
            )
            for ca in concert.concert_artists
            if ca.artist
        ]
        
        return cls(
            id=concert.id,
            date=concert.date.isoformat() if hasattr(concert.date, 'isoformat') else str(concert.date),
            location=concert.location,
            description=concert.description,
            facebook_event_id=concert.facebook_event_id,
            version=concert.version,
            created_at=concert.created_at.isoformat() if hasattr(concert.created_at, 'isoformat') else str(concert.created_at),
            updated_at=concert.updated_at.isoformat() if hasattr(concert.updated_at, 'isoformat') else str(concert.updated_at),
            artists=artists
        )


@router.get("", response_model=List[ConcertResponse])
async def list_concerts(
    upcoming_only: bool = Query(False, description="Filter to show only upcoming concerts"),
    db: AsyncSession = Depends(get_db)
) -> List[ConcertResponse]:
    """List all concerts, sorted by date (chronological order)."""
    logger.info("listing_concerts", upcoming_only=upcoming_only)
    
    service = ConcertService(db)
    concerts = await service.get_all_concerts(upcoming_only=upcoming_only)
    
    logger.info("concerts_listed", count=len(concerts))
    return [ConcertResponse.from_orm_with_artists(concert) for concert in concerts]


@router.get("/{concert_id}", response_model=ConcertResponse)
async def get_concert(
    concert_id: UUID,
    db: AsyncSession = Depends(get_db)
) -> ConcertResponse:
    """Get a concert by ID."""
    logger.info("getting_concert", concert_id=str(concert_id))
    
    service = ConcertService(db)
    concert = await service.get_concert_by_id(concert_id)
    
    if not concert:
        logger.warning("concert_not_found", concert_id=str(concert_id))
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Concert {concert_id} not found"
        )
    
    logger.info("concert_retrieved", concert_id=str(concert_id), location=concert.location)
    return ConcertResponse.from_orm_with_artists(concert)

