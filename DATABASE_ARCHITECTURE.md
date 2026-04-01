# Multimodal Traffic Intelligence Platform - Database Architecture

## Overview
Complete production-grade database layer with async SQLAlchemy, PostgreSQL schema, and analytics materialized views.

## Directory Structure

```
backend/database/
├── __init__.py           # Module exports
├── connection.py         # AsyncSessionFactory, FastAPI dependency injection
├── models.py            # SQLAlchemy ORM models (6 models)
└── queries.py           # Async query helpers (7 query functions)

db/
└── init.sql             # PostgreSQL schema (463 lines, 5 materialized views)
```

## Core Components

### 1. Connection Management (`connection.py`)
- **AsyncSessionFactory**: Connection pool with configurable size/overflow
- **get_db()**: FastAPI dependency for request-scoped sessions
- **health_check()**: Database connectivity verification
- **Connection pooling**: QueuePool with pre-ping, recycle, and timeout configuration

#### Key Features:
- Async context managers for automatic transaction handling
- Connection pooling with 20 connections default, 10 overflow
- Connection recycling every 3600 seconds
- Query echo for development debugging

### 2. Data Models (`models.py`)
Six production-grade ORM models with relationships:

#### DetectionEvent
Vehicle detection from object detection model
- Bounding boxes (normalized 0.0-1.0 coordinates)
- Confidence scores, vehicle type, tracking
- Speed estimates and direction
- Comprehensive indexes on session/timestamp/track

#### IncidentEvent
High-level traffic incidents (collisions, congestion, hazards)
- Severity levels (low/medium/high/critical)
- Related track IDs, location descriptions
- Resolution tracking with timestamps
- Unresolved index for quick filtering

#### TrafficSession
Monitoring session representing continuous data source
- Source types (video file, RTSP, camera feed, etc.)
- Status tracking (active/completed/failed/paused)
- Flexible JSONB metadata storage
- Relationships to all other entities

#### VehicleCount
Aggregated counts by interval (e.g., hourly summaries)
- Configurable interval duration
- Direction-based filtering
- Unique constraints prevent duplicates
- Optimized for time-series queries

#### TrafficReport
Generated analytics and summaries
- Report types: summary, detailed, incident_analysis
- Flexible JSONB content structure
- Query tracking for reproducibility
- Time-indexed for fast retrieval

#### Base & Enums
- Enum types: SourceType, VehicleType, IncidentType, SeverityLevel, SessionStatus
- Declarative base for SQLAlchemy ORM

### 3. Query Helpers (`queries.py`)
Seven async query functions for common operations:

#### get_detection_summary()
- Total detection counts
- Unique vehicle tracking
- Vehicle type breakdown
- Confidence statistics (min/max/avg)
- Optional time range filtering

#### get_vehicle_counts()
- Pre-computed vehicle counts by interval
- Vehicle type and direction filtering
- Chronological ordering

#### get_incidents()
- Flexible incident filtering (type, severity, resolution status)
- Result limiting (default 1000)
- Reverse chronological ordering

#### get_traffic_flow()
- Speed analysis (average, min, max)
- Direction distribution
- Vehicle type distribution
- Peak activity time calculation

#### search_events()
- Multi-parameter detection event search
- Vehicle type, confidence, track ID filtering
- Time range support
- Scalable result limiting

#### get_session_stats()
- Comprehensive session overview
- Detection and incident summaries
- Temporal metrics (duration, start/end)
- Quality metrics

### 4. PostgreSQL Schema (`init.sql`)
Production schema with 463 lines including:

#### Tables (6 total)
- **traffic_sessions**: 11 columns, 5 indexes
- **detection_events**: 14 columns, 7 indexes
- **incident_events**: 13 columns, 6 indexes
- **vehicle_counts**: 8 columns, 5 indexes
- **traffic_reports**: 6 columns, 4 indexes

#### Constraints
- Check constraints for valid ranges (confidence 0-1, bbox 0-1)
- Foreign key cascades for data integrity
- Unique constraints for vehicle_counts (no duplicates)
- Temporal constraints (end_time > start_time)

#### Indexes (27 total)
- Composite indexes for common query patterns
- Session + timestamp indexes for time-range queries
- Covering indexes for aggregations
- Partial indexes for resolved/unresolved incidents

#### Materialized Views (5)
1. **mv_hourly_traffic_summary**: Traffic aggregated by hour and vehicle type
   - Detection counts, confidence, speed statistics
   - Indexed for fast access

2. **mv_incident_summary**: Incident statistics by type and severity
   - Count, resolution metrics
   - Average resolution time calculation

3. **mv_vehicle_distribution**: Vehicle count aggregations
   - Total counts, averages, peaks by direction
   - Distribution analysis

4. **mv_peak_hours**: Hourly traffic patterns
   - Hour-of-day analysis
   - Unique vehicle counts
   - Confidence metrics

5. **mv_session_quality_metrics**: Overall session statistics
   - Detection confidence ranges
   - Incident summaries
   - Session duration and metadata

#### Utility Functions (3)
1. **get_session_traffic_stats()**: Aggregate statistics with optional time filtering
2. **detect_speed_anomalies()**: Find vehicles with unusual speed patterns
3. **refresh_all_materialized_views()**: Concurrent refresh of all views

#### Triggers (2)
- **update_updated_at_column()**: Auto-manages timestamp updates
- Applied to traffic_sessions and incident_events

## Type System

### Enumerations
```python
VehicleType: car, truck, bus, motorcycle, bicycle, pedestrian, van, unknown
IncidentType: collision, congestion, stalled_vehicle, hazard, unusual_activity, weather_related, infrastructure_damage, other
SeverityLevel: low, medium, high, critical
SourceType: video_stream, video_file, camera_feed, rtsp, http_stream, file_upload
SessionStatus: active, completed, failed, paused
```

## Performance Optimizations

1. **Indexing Strategy**
   - Single-column indexes for WHERE clauses
   - Composite indexes for common joins
   - Partial indexes for frequent filters

2. **Query Optimization**
   - Lazy loading of relationships
   - Efficient aggregation with materialized views
   - Pre-computed statistics for dashboards

3. **Connection Management**
   - Connection pooling (20 connections, 10 overflow)
   - Pre-ping for stale connection detection
   - Automatic connection recycling

4. **Data Integrity**
   - Check constraints for valid ranges
   - Foreign key cascades for consistency
   - Unique constraints for deduplication

## Security

- Read-only analytics role with SELECT privileges
- Application role with full table/sequence/function access
- Schema-level permission management

## Usage Examples

### FastAPI Integration
```python
from fastapi import FastAPI, Depends
from database import get_db, init_db
from sqlalchemy.ext.asyncio import AsyncSession

app = FastAPI()

@app.on_event("startup")
async def startup():
    init_db("postgresql+asyncpg://user:pass@localhost/traffic_db")

@app.get("/sessions/{session_id}/stats")
async def get_stats(session_id: str, db: AsyncSession = Depends(get_db)):
    return await get_session_stats(db, session_id)
```

### Direct Query Usage
```python
from database import get_detection_summary, get_incidents

async with factory.session_context() as session:
    summary = await get_detection_summary(session, session_id)
    incidents = await get_incidents(session, session_id, severity="high")
```

## Deployment Checklist

- [ ] PostgreSQL 13+ installed with asyncpg driver
- [ ] Create database: `createdb traffic_intelligence`
- [ ] Run init.sql: `psql traffic_intelligence < init.sql`
- [ ] Create application user with proper permissions
- [ ] Configure connection pool size based on expected load
- [ ] Enable query logging for performance monitoring
- [ ] Set up automated materialized view refresh (via cron or application)
- [ ] Configure database backups and replication

## Monitoring & Maintenance

- Monitor connection pool utilization
- Refresh materialized views regularly (recommended: hourly)
- Monitor slow query log for optimization opportunities
- Regular VACUUM and ANALYZE for query planner
- Index fragmentation monitoring (pg_stat_user_indexes)

