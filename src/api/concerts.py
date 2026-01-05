"""Concert API endpoints."""
from fastapi import APIRouter, Depends, HTTPException, status, Query, Header
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel
from cloudsound_shared.db.pool import get_db
from ..services.concert_service import ConcertService, ConcertConflictError
from ..models import Concert, ConcertArtist
from cloudsound_shared.logging import get_logger
from cloudsound_shared.jwt_handler import verify_token, TokenData

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


class ConcertCreateRequest(BaseModel):
    """Request model for creating a concert."""
    date: datetime
    location: str
    description: Optional[str] = None
    facebook_event_id: Optional[str] = None
    artist_ids: Optional[List[UUID]] = None


class ConcertUpdateRequest(BaseModel):
    """Request model for updating a concert."""
    date: Optional[datetime] = None
    location: Optional[str] = None
    description: Optional[str] = None
    facebook_event_id: Optional[str] = None
    artist_ids: Optional[List[UUID]] = None
    expected_version: Optional[int] = None


async def require_admin(authorization: Optional[str] = Header(None)) -> TokenData:
    """Dependency to ensure the caller is an authenticated admin."""
    if not authorization or not authorization.lower().startswith("bearer "):
        logger.warning("missing_authorization_header")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
        )

    token = authorization.split(" ", 1)[1]
    token_data = verify_token(token)

    if not token_data:
        logger.warning("invalid_token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    if token_data.role != "admin":
        logger.warning("admin_required", user_id=token_data.user_id, role=token_data.role)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )

    return token_data


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


@router.post("", response_model=ConcertResponse, status_code=status.HTTP_201_CREATED)
async def create_concert(
    request: ConcertCreateRequest,
    db: AsyncSession = Depends(get_db),
    admin: TokenData = Depends(require_admin),
) -> ConcertResponse:
    """Create a new concert (admin only)."""
    logger.info("creating_concert", location=request.location, admin_id=admin.user_id)

    service = ConcertService(db)
    concert = await service.create_concert(
        date=request.date,
        location=request.location,
        description=request.description,
        artist_ids=request.artist_ids,
        facebook_event_id=request.facebook_event_id,
    )

    logger.info("concert_created", concert_id=str(concert.id), admin_id=admin.user_id)
    return ConcertResponse.from_orm_with_artists(concert)


@router.put("/{concert_id}", response_model=ConcertResponse)
async def update_concert(
    concert_id: UUID,
    request: ConcertUpdateRequest,
    db: AsyncSession = Depends(get_db),
    admin: TokenData = Depends(require_admin),
) -> ConcertResponse:
    """Update an existing concert (admin only) with optimistic locking."""
    logger.info(
        "updating_concert",
        concert_id=str(concert_id),
        admin_id=admin.user_id,
        expected_version=request.expected_version,
    )

    service = ConcertService(db)
    try:
        concert = await service.update_concert(
            concert_id=concert_id,
            date=request.date,
            location=request.location,
            description=request.description,
            artist_ids=request.artist_ids,
            facebook_event_id=request.facebook_event_id,
            expected_version=request.expected_version,
        )
    except ConcertConflictError as exc:
        logger.warning(
            "concert_update_conflict",
            concert_id=str(concert_id),
            admin_id=admin.user_id,
            error=str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        logger.warning(
            "concert_update_not_found",
            concert_id=str(concert_id),
            admin_id=admin.user_id,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    logger.info("concert_updated", concert_id=str(concert_id), admin_id=admin.user_id, version=concert.version)
    return ConcertResponse.from_orm_with_artists(concert)


@router.delete("/{concert_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_concert(
    concert_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin: TokenData = Depends(require_admin),
) -> None:
    """Delete a concert (admin only)."""
    logger.info("deleting_concert", concert_id=str(concert_id), admin_id=admin.user_id)

    service = ConcertService(db)
    deleted = await service.delete_concert(concert_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Concert {concert_id} not found",
        )

    logger.info("concert_deleted", concert_id=str(concert_id), admin_id=admin.user_id)
    return None

