"""Concert service for managing concerts."""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload
from typing import List, Optional
from uuid import UUID
from datetime import datetime
from ..models import Concert, ConcertArtist
from cloudsound_shared.logging import get_logger

logger = get_logger(__name__)


class ConcertConflictError(Exception):
    """Raised when a concert update conflicts with another update."""
    pass


class ConcertService:
    """Service for managing concerts."""
    
    def __init__(self, db: AsyncSession):
        """Initialize service with database session."""
        self.db = db
    
    async def get_all_concerts(self, upcoming_only: bool = False) -> List[Concert]:
        """Get all concerts, optionally filtering by upcoming dates only."""
        query = select(Concert)
        
        if upcoming_only:
            from datetime import timezone
            now = datetime.now(timezone.utc)
            query = query.where(Concert.date >= now)
        
        # Sort by date (chronological order)
        query = query.order_by(Concert.date.asc())
        
        # Load concert_artists relationships
        query = query.options(
            selectinload(Concert.concert_artists)
        )
        
        result = await self.db.execute(query)
        concerts = result.scalars().all()
        
        # Manually load artists for each concert_artist using raw SQL
        # This avoids import issues with radio-streaming service
        from sqlalchemy import text
        
        class MinimalArtist:
            """Minimal artist object for response."""
            def __init__(self, artist_id, name=None, genre=None):
                self.id = artist_id
                self.name = name or "Unknown Artist"
                self.genre = genre
        
        # Collect all artist IDs
        artist_ids = set()
        for concert in concerts:
            for ca in concert.concert_artists:
                artist_ids.add(ca.artist_id)
        
        # Load all artists in one query
        if artist_ids:
            artist_ids_list = list(artist_ids)
            placeholders = ','.join([f"'{str(aid)}'" for aid in artist_ids_list])
            result = await self.db.execute(
                text(f"SELECT id, name, genre FROM artists WHERE id IN ({placeholders})")
            )
            artists_dict = {row[0]: MinimalArtist(row[0], row[1], row[2]) for row in result.fetchall()}
            
            # Assign artists to concert_artists
            for concert in concerts:
                for ca in concert.concert_artists:
                    ca.artist = artists_dict.get(ca.artist_id, MinimalArtist(ca.artist_id))
        else:
            # No artists to load
            for concert in concerts:
                for ca in concert.concert_artists:
                    ca.artist = MinimalArtist(ca.artist_id)
        
        logger.info("retrieved_concerts", count=len(concerts), upcoming_only=upcoming_only)
        return list(concerts)
    
    async def get_concert_by_id(self, concert_id: UUID) -> Optional[Concert]:
        """Get a concert by ID."""
        query = select(Concert).where(Concert.id == concert_id)
        query = query.options(
            selectinload(Concert.concert_artists)
        )
        
        result = await self.db.execute(query)
        concert = result.scalar_one_or_none()
        
        if concert:
            # Manually load artists
            from backend.radio_streaming.src.models.artist import Artist
            for ca in concert.concert_artists:
                artist_query = select(Artist).where(Artist.id == ca.artist_id)
                artist_result = await self.db.execute(artist_query)
                ca.artist = artist_result.scalar_one_or_none()
            
            logger.info("retrieved_concert", concert_id=str(concert_id), location=concert.location)
        else:
            logger.warning("concert_not_found", concert_id=str(concert_id))
        
        return concert
    
    async def get_concerts_by_date_range(
        self, 
        start_date: datetime, 
        end_date: datetime
    ) -> List[Concert]:
        """Get concerts within a date range."""
        query = select(Concert).where(
            and_(
                Concert.date >= start_date,
                Concert.date <= end_date
            )
        )
        
        # Sort by date (chronological order)
        query = query.order_by(Concert.date.asc())
        
        query = query.options(
            selectinload(Concert.concert_artists).selectinload(ConcertArtist.artist)
        )
        
        result = await self.db.execute(query)
        concerts = result.scalars().all()
        
        logger.info(
            "retrieved_concerts_by_date_range",
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
            count=len(concerts)
        )
        return list(concerts)
    
    async def create_concert(
        self,
        date: datetime,
        location: str,
        description: Optional[str] = None,
        artist_ids: Optional[List[UUID]] = None,
        facebook_event_id: Optional[str] = None
    ) -> Concert:
        """Create a new concert."""
        concert = Concert(
            date=date,
            location=location,
            description=description,
            facebook_event_id=facebook_event_id,
            version=1
        )
        
        self.db.add(concert)
        await self.db.flush()  # Get the concert ID
        
        # Add artists if provided
        if artist_ids:
            for artist_id in artist_ids:
                concert_artist = ConcertArtist(
                    concert_id=concert.id,
                    artist_id=artist_id
                )
                self.db.add(concert_artist)
        
        await self.db.commit()
        await self.db.refresh(concert)
        
        # Reload with relationships
        await self.db.refresh(concert, ["concert_artists"])
        for ca in concert.concert_artists:
            await self.db.refresh(ca, ["artist"])
        
        logger.info("created_concert", concert_id=str(concert.id), location=location)
        return concert
    
    async def update_concert(
        self,
        concert_id: UUID,
        date: Optional[datetime] = None,
        location: Optional[str] = None,
        description: Optional[str] = None,
        artist_ids: Optional[List[UUID]] = None,
        facebook_event_id: Optional[str] = None,
        expected_version: Optional[int] = None
    ) -> Concert:
        """Update a concert with optimistic locking conflict detection."""
        concert = await self.get_concert_by_id(concert_id)
        
        if not concert:
            raise ValueError(f"Concert {concert_id} not found")
        
        # Check for version conflict if expected_version is provided
        if expected_version is not None and concert.version != expected_version:
            logger.warning(
                "concert_version_conflict",
                concert_id=str(concert_id),
                expected_version=expected_version,
                actual_version=concert.version
            )
            raise ConcertConflictError(
                f"Concert {concert_id} has been modified. Expected version {expected_version}, "
                f"but current version is {concert.version}"
            )
        
        # Update fields
        if date is not None:
            concert.date = date
        if location is not None:
            concert.location = location
        if description is not None:
            concert.description = description
        if facebook_event_id is not None:
            concert.facebook_event_id = facebook_event_id
        
        # Increment version for optimistic locking
        concert.version += 1
        
        # Update artists if provided
        if artist_ids is not None:
            # Remove existing artist associations
            result = await self.db.execute(
                select(ConcertArtist).where(ConcertArtist.concert_id == concert_id)
            )
            existing_artists = result.scalars().all()
            for ca in existing_artists:
                await self.db.delete(ca)
            
            # Add new artist associations
            for artist_id in artist_ids:
                concert_artist = ConcertArtist(
                    concert_id=concert.id,
                    artist_id=artist_id
                )
                self.db.add(concert_artist)
        
        await self.db.commit()
        await self.db.refresh(concert)
        
        # Reload with relationships
        await self.db.refresh(concert, ["concert_artists"])
        for ca in concert.concert_artists:
            await self.db.refresh(ca, ["artist"])
        
        logger.info("updated_concert", concert_id=str(concert_id), version=concert.version)
        return concert
    
    async def delete_concert(self, concert_id: UUID) -> bool:
        """Delete a concert."""
        concert = await self.get_concert_by_id(concert_id)
        
        if not concert:
            logger.warning("concert_not_found_for_delete", concert_id=str(concert_id))
            return False
        
        await self.db.delete(concert)
        await self.db.commit()
        
        logger.info("deleted_concert", concert_id=str(concert_id))
        return True

