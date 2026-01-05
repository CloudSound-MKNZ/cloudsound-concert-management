#!/usr/bin/env python3
"""Seed concerts for testing."""
import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from cloudsound_shared.db.pool import AsyncSessionLocal
from sqlalchemy import text
from datetime import datetime, timedelta, timezone

async def seed_concerts():
    async with AsyncSessionLocal() as session:
        # Check if past concerts already exist
        result = await session.execute(text("SELECT COUNT(*) FROM concerts WHERE date < NOW()"))
        past_count = result.scalar()
        if past_count >= 3:
            print(f"✅ {past_count} past concerts already exist")
            return
        
        # Check total concerts
        result = await session.execute(text("SELECT COUNT(*) FROM concerts"))
        total_count = result.scalar()
        print(f"Found {total_count} existing concerts, adding past concerts...")
        
        # Get all artist IDs
        result = await session.execute(text("SELECT id FROM artists"))
        all_artist_ids = [row[0] for row in result.fetchall()]
        
        if len(all_artist_ids) < 5:
            print("❌ Need at least 5 artists. Run seed-mock-data.py first.")
            return
        
        # Use first 5 artists for upcoming concerts, rest for past concerts
        artist_ids = all_artist_ids[:5]
        past_artist_ids = all_artist_ids[5:] if len(all_artist_ids) > 5 else all_artist_ids[2:5]
        
        # Create first concert using raw SQL
        concert1_date = datetime.now(timezone.utc) + timedelta(days=7)
        await session.execute(text("""
            INSERT INTO concerts (id, date, location, description, version, created_at, updated_at)
            VALUES (gen_random_uuid(), :date, 'Main Stage', 'A great summer music festival featuring local artists.', 1, NOW(), NOW())
            RETURNING id
        """), {"date": concert1_date})
        
        result = await session.execute(text("SELECT id FROM concerts ORDER BY created_at DESC LIMIT 1"))
        concert1_id = result.scalar()
        
        # Link artists to first concert
        for artist_id in artist_ids[:3]:
            await session.execute(text("""
                INSERT INTO concert_artists (id, concert_id, artist_id, created_at, updated_at)
                VALUES (gen_random_uuid(), :concert_id, :artist_id, NOW(), NOW())
            """), {"concert_id": concert1_id, "artist_id": artist_id})
        
        # Create second concert
        concert2_date = datetime.now(timezone.utc) + timedelta(days=14)
        await session.execute(text("""
            INSERT INTO concerts (id, date, location, description, version, created_at, updated_at)
            VALUES (gen_random_uuid(), :date, 'Outdoor Venue', 'Rock night with amazing local bands.', 1, NOW(), NOW())
            RETURNING id
        """), {"date": concert2_date})
        
        result = await session.execute(text("SELECT id FROM concerts ORDER BY created_at DESC LIMIT 1"))
        concert2_id = result.scalar()
        
        # Link different artists to second concert
        for artist_id in artist_ids[3:5] if len(artist_ids) >= 5 else artist_ids[1:3]:
            await session.execute(text("""
                INSERT INTO concert_artists (id, concert_id, artist_id, created_at, updated_at)
                VALUES (gen_random_uuid(), :concert_id, :artist_id, NOW(), NOW())
            """), {"concert_id": concert2_id, "artist_id": artist_id})
        
        # Create past concerts (already happened - before Dec 10, 2025)
        # Past concert 1 - November 15, 2025 (25 days ago)
        past_date1 = datetime(2025, 11, 15, 20, 0, 0, tzinfo=timezone.utc)
        await session.execute(text("""
            INSERT INTO concerts (id, date, location, description, version, created_at, updated_at)
            VALUES (gen_random_uuid(), :date, 'Local Venue', 'Amazing show that happened last month!', 1, NOW(), NOW())
            RETURNING id
        """), {"date": past_date1})
        
        result = await session.execute(text("SELECT id FROM concerts ORDER BY created_at DESC LIMIT 1"))
        past_concert1_id = result.scalar()
        
        # Link artists to past concert 1 (use different artists)
        for artist_id in past_artist_ids[:2] if len(past_artist_ids) >= 2 else all_artist_ids[3:5]:
            await session.execute(text("""
                INSERT INTO concert_artists (id, concert_id, artist_id, created_at, updated_at)
                VALUES (gen_random_uuid(), :concert_id, :artist_id, NOW(), NOW())
                ON CONFLICT (concert_id, artist_id) DO NOTHING
            """), {"concert_id": past_concert1_id, "artist_id": artist_id})
        
        # Past concert 2 - October 20, 2025 (51 days ago)
        past_date2 = datetime(2025, 10, 20, 19, 30, 0, tzinfo=timezone.utc)
        await session.execute(text("""
            INSERT INTO concerts (id, date, location, description, version, created_at, updated_at)
            VALUES (gen_random_uuid(), :date, 'Community Center', 'Great performance from earlier this year.', 1, NOW(), NOW())
            RETURNING id
        """), {"date": past_date2})
        
        result = await session.execute(text("SELECT id FROM concerts ORDER BY created_at DESC LIMIT 1"))
        past_concert2_id = result.scalar()
        
        # Link artists to past concert 2 (use different artists)
        for artist_id in past_artist_ids[2:4] if len(past_artist_ids) >= 4 else all_artist_ids[1:3]:
            await session.execute(text("""
                INSERT INTO concert_artists (id, concert_id, artist_id, created_at, updated_at)
                VALUES (gen_random_uuid(), :concert_id, :artist_id, NOW(), NOW())
                ON CONFLICT (concert_id, artist_id) DO NOTHING
            """), {"concert_id": past_concert2_id, "artist_id": artist_id})
        
        # Past concert 3 - September 25, 2025 (76 days ago)
        past_date3 = datetime(2025, 9, 25, 21, 0, 0, tzinfo=timezone.utc)
        await session.execute(text("""
            INSERT INTO concerts (id, date, location, description, version, created_at, updated_at)
            VALUES (gen_random_uuid(), :date, 'Music Hall', 'Epic night of live music!', 1, NOW(), NOW())
            RETURNING id
        """), {"date": past_date3})
        
        result = await session.execute(text("SELECT id FROM concerts ORDER BY created_at DESC LIMIT 1"))
        past_concert3_id = result.scalar()
        
        # Link artists to past concert 3 (use remaining artists)
        remaining_artists = [aid for aid in all_artist_ids if aid not in artist_ids[:3] and aid not in past_artist_ids[:4]]
        if remaining_artists:
            for artist_id in remaining_artists[:2]:
                await session.execute(text("""
                    INSERT INTO concert_artists (id, concert_id, artist_id, created_at, updated_at)
                    VALUES (gen_random_uuid(), :concert_id, :artist_id, NOW(), NOW())
                    ON CONFLICT (concert_id, artist_id) DO NOTHING
                """), {"concert_id": past_concert3_id, "artist_id": artist_id})
        else:
            # Fallback: use any available artist
            for artist_id in all_artist_ids[:1]:
                await session.execute(text("""
                    INSERT INTO concert_artists (id, concert_id, artist_id, created_at, updated_at)
                    VALUES (gen_random_uuid(), :concert_id, :artist_id, NOW(), NOW())
                    ON CONFLICT (concert_id, artist_id) DO NOTHING
                """), {"concert_id": past_concert3_id, "artist_id": artist_id})
        
        await session.commit()
        print(f"✅ Created 2 upcoming concerts and 3 past concerts")

if __name__ == "__main__":
    asyncio.run(seed_concerts())

