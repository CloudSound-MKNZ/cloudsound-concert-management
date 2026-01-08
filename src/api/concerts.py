"""Concert API endpoints."""
from fastapi import APIRouter, Depends, HTTPException, status, Query, Header
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from uuid import UUID
from datetime import datetime, timezone
from pydantic import BaseModel, Field, field_validator, ConfigDict

from cloudsound_shared.multitenancy import get_tenant_db
from cloudsound_shared.logging import get_logger
from cloudsound_shared.jwt_handler import verify_token, TokenData
from cloudsound_shared.exceptions import (
    NotFoundError,
    OptimisticLockError,
    AuthenticationError,
    AuthorizationError,
)

from ..services.concert_service import ConcertService, ConcertConflictError
from ..models import Concert, ConcertArtist
from ..producers.kafka_producer import get_concert_producer

logger = get_logger(__name__)

router = APIRouter(prefix="/concerts", tags=["concerts"])


class ArtistResponse(BaseModel):
    """Artist response model."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    name: str
    genre: Optional[str] = None


class ConcertArtistResponse(BaseModel):
    """ConcertArtist response model."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    artist_id: UUID
    artist: Optional[ArtistResponse] = None


class ConcertResponse(BaseModel):
    """Concert response model."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    date: str  # ISO format string
    location: str
    description: Optional[str] = None
    facebook_event_id: Optional[str] = None
    version: int
    created_at: str  # ISO format string
    updated_at: str  # ISO format string
    artists: List[ArtistResponse] = []
    
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
    """Request model for creating a concert with validation."""
    date: datetime = Field(..., description="Concert date and time")
    location: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Concert venue/location",
    )
    description: Optional[str] = Field(
        None,
        max_length=5000,
        description="Concert description",
    )
    facebook_event_id: Optional[str] = Field(
        None,
        max_length=50,
        pattern=r"^\d+$",
        description="Facebook event ID (numeric)",
    )
    artist_ids: Optional[List[UUID]] = Field(
        None,
        description="List of artist UUIDs performing at this concert",
    )
    
    @field_validator("date")
    @classmethod
    def validate_date_not_in_past(cls, v: datetime) -> datetime:
        """Validate that concert date is not in the past."""
        # Allow dates in the past for historical records, but warn
        # In strict mode, you could raise an error for past dates
        return v
    
    @field_validator("location")
    @classmethod
    def validate_location_not_empty(cls, v: str) -> str:
        """Validate that location is not just whitespace."""
        stripped = v.strip()
        if not stripped:
            raise ValueError("Location cannot be empty or whitespace only")
        return stripped
    
    @field_validator("artist_ids")
    @classmethod
    def validate_artist_ids_unique(cls, v: Optional[List[UUID]]) -> Optional[List[UUID]]:
        """Validate that artist IDs are unique."""
        if v is not None:
            if len(v) != len(set(v)):
                raise ValueError("Artist IDs must be unique")
        return v


class ConcertUpdateRequest(BaseModel):
    """Request model for updating a concert with validation."""
    date: Optional[datetime] = Field(None, description="Concert date and time")
    location: Optional[str] = Field(
        None,
        min_length=1,
        max_length=500,
        description="Concert venue/location",
    )
    description: Optional[str] = Field(
        None,
        max_length=5000,
        description="Concert description",
    )
    facebook_event_id: Optional[str] = Field(
        None,
        max_length=50,
        pattern=r"^\d+$",
        description="Facebook event ID (numeric)",
    )
    artist_ids: Optional[List[UUID]] = Field(
        None,
        description="List of artist UUIDs performing at this concert",
    )
    expected_version: Optional[int] = Field(
        None,
        ge=1,
        description="Expected version for optimistic locking",
    )
    
    @field_validator("location")
    @classmethod
    def validate_location_not_empty(cls, v: Optional[str]) -> Optional[str]:
        """Validate that location is not just whitespace."""
        if v is not None:
            stripped = v.strip()
            if not stripped:
                raise ValueError("Location cannot be empty or whitespace only")
            return stripped
        return v
    
    @field_validator("artist_ids")
    @classmethod
    def validate_artist_ids_unique(cls, v: Optional[List[UUID]]) -> Optional[List[UUID]]:
        """Validate that artist IDs are unique."""
        if v is not None:
            if len(v) != len(set(v)):
                raise ValueError("Artist IDs must be unique")
        return v


async def require_admin(authorization: Optional[str] = Header(None)) -> TokenData:
    """Dependency to ensure the caller is an authenticated admin."""
    if not authorization or not authorization.lower().startswith("bearer "):
        logger.warning(
            "missing_authorization_header",
            received_header=authorization[:50] if authorization else None,
        )
        raise AuthenticationError(
            message="Missing or invalid Authorization header",
            details={"header": "Authorization"},
        )

    token = authorization.split(" ", 1)[1]
    logger.debug("verifying_token", token_prefix=token[:20] if len(token) > 20 else token)
    token_data = verify_token(token)

    if not token_data:
        logger.warning(
            "invalid_token",
            token_length=len(token),
            token_parts=len(token.split(".")),
        )
        raise AuthenticationError(
            message="Invalid or expired token",
        )

    if token_data.role != "admin":
        logger.warning("admin_required", user_id=token_data.user_id, role=token_data.role)
        raise AuthorizationError(
            message="Admin privileges required",
            details={"required_role": "admin", "current_role": token_data.role},
        )

    return token_data


@router.get("", response_model=List[ConcertResponse])
async def list_concerts(
    upcoming_only: bool = Query(False, description="Filter to show only upcoming concerts"),
    db: AsyncSession = Depends(get_tenant_db)
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
    db: AsyncSession = Depends(get_tenant_db)
) -> ConcertResponse:
    """Get a concert by ID."""
    logger.info("getting_concert", concert_id=str(concert_id))
    
    service = ConcertService(db)
    concert = await service.get_concert_by_id(concert_id)
    
    if not concert:
        logger.warning("concert_not_found", concert_id=str(concert_id))
        raise NotFoundError(
            message=f"Concert {concert_id} not found",
            details={"concert_id": str(concert_id)},
        )
    
    logger.info("concert_retrieved", concert_id=str(concert_id), location=concert.location)
    return ConcertResponse.from_orm_with_artists(concert)


@router.post("", response_model=ConcertResponse, status_code=status.HTTP_201_CREATED)
async def create_concert(
    request: ConcertCreateRequest,
    db: AsyncSession = Depends(get_tenant_db),
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
    
    # Publish concert.created event to Kafka for music discovery
    try:
        producer = get_concert_producer()
        artist_names = [
            ca.artist.name for ca in concert.concert_artists if ca.artist
        ]
        producer.publish_concert_created(
            concert_id=concert.id,
            location=concert.location,
            date=concert.date,
            description=concert.description,
            artists=artist_names,
            facebook_event_id=concert.facebook_event_id,
        )
        logger.info(
            "concert_created_event_published",
            concert_id=str(concert.id),
        )
    except Exception as e:
        # Log but don't fail the request - music discovery is non-critical
        logger.warning(
            "failed_to_publish_concert_created_event",
            concert_id=str(concert.id),
            error=str(e),
        )
    
    return ConcertResponse.from_orm_with_artists(concert)


@router.put("/{concert_id}", response_model=ConcertResponse)
async def update_concert(
    concert_id: UUID,
    request: ConcertUpdateRequest,
    db: AsyncSession = Depends(get_tenant_db),
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
        raise OptimisticLockError(
            message=str(exc),
            details={"concert_id": str(concert_id)},
        ) from exc
    except ValueError as exc:
        logger.warning(
            "concert_update_not_found",
            concert_id=str(concert_id),
            admin_id=admin.user_id,
        )
        raise NotFoundError(
            message=str(exc),
            details={"concert_id": str(concert_id)},
        ) from exc

    logger.info("concert_updated", concert_id=str(concert_id), admin_id=admin.user_id, version=concert.version)
    
    # Publish concert.updated event to Kafka for music discovery
    try:
        producer = get_concert_producer()
        artist_names = [
            ca.artist.name for ca in concert.concert_artists if ca.artist
        ]
        producer.publish_concert_updated(
            concert_id=concert.id,
            location=concert.location,
            date=concert.date,
            description=concert.description,
            artists=artist_names,
            facebook_event_id=concert.facebook_event_id,
        )
        logger.info(
            "concert_updated_event_published",
            concert_id=str(concert.id),
        )
    except Exception as e:
        # Log but don't fail the request
        logger.warning(
            "failed_to_publish_concert_updated_event",
            concert_id=str(concert.id),
            error=str(e),
        )
    
    return ConcertResponse.from_orm_with_artists(concert)


@router.delete("/{concert_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_concert(
    concert_id: UUID,
    db: AsyncSession = Depends(get_tenant_db),
    admin: TokenData = Depends(require_admin),
) -> None:
    """Delete a concert (admin only)."""
    logger.info("deleting_concert", concert_id=str(concert_id), admin_id=admin.user_id)

    service = ConcertService(db)
    deleted = await service.delete_concert(concert_id)
    if not deleted:
        raise NotFoundError(
            message=f"Concert {concert_id} not found",
            details={"concert_id": str(concert_id)},
        )

    logger.info("concert_deleted", concert_id=str(concert_id), admin_id=admin.user_id)
    return None

