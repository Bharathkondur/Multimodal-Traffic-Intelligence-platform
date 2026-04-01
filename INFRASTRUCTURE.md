# Infrastructure Documentation

## Overview

The Multimodal Traffic Intelligence Platform uses a containerized microservices architecture with Docker Compose. This document describes all infrastructure components and how they work together.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Traffic Intelligence Platform           │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │   Frontend   │  │   Backend    │  │   Grafana        │   │
│  │  (React SPA) │  │   (FastAPI)  │  │  (Dashboards)    │   │
│  │  Nginx 80    │  │  Uvicorn 8k  │  │  Port 3001       │   │
│  └──────┬───────┘  └──────┬───────┘  └─────────┬────────┘   │
│         │                 │                    │             │
│         └─────────────────┼────────────────────┘             │
│                           │                                   │
│          traffic-net (Docker Bridge Network)                 │
│                           │                                   │
│         ┌─────────────────┼─────────────────┐                │
│         │                 │                 │                │
│    ┌────▼────┐      ┌─────▼──────┐   ┌────▼────┐            │
│    │PostgreSQL│      │   Redis    │   │ Uploads │            │
│    │   Port   │      │Port 6379   │   │ Volume  │            │
│    │   5432   │      │(caching)   │   │         │            │
│    └─────┬────┘      └────────────┘   └─────────┘            │
│          │                                                    │
│      postgres-data volume (persistent)                       │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

## Services

### Frontend (Nginx + React)

**Container:** `traffic-frontend`
**Port:** 3000:80
**Image:** Built from `Dockerfile.frontend`

Features:
- Multi-stage Docker build (node:20-alpine for build, nginx:alpine for serve)
- React SPA with Vite bundler
- SPA fallback routing (all routes serve index.html)
- API proxy to backend at `/api/`
- WebSocket proxy for real-time updates at `/ws`
- Gzip compression for all text assets
- Security headers (HSTS, X-Frame-Options, X-Content-Type-Options, etc.)
- Rate limiting (general and API-specific)
- Static asset caching (1-year expiration for versioned assets)

**Configuration File:** `nginx.conf`

### Backend (FastAPI)

**Container:** `traffic-backend`
**Port:** 8000:8000
**Image:** Built from `Dockerfile.backend`

Features:
- Multi-stage Docker build for optimal image size
- Python 3.11-slim base
- Non-root user execution (appuser:1000)
- Health check endpoint at `/health`
- System dependencies for OpenCV (libgl1, libglib2.0-0)
- Uvicorn ASGI server with 4 workers
- Environment variable configuration

**Key Dependencies:**
- FastAPI for web framework
- SQLAlchemy for ORM
- OpenCV for computer vision
- YOLOv8 for object detection
- OpenAI/Ollama for LLM integration
- Redis for caching

### PostgreSQL Database

**Container:** `traffic-postgres`
**Port:** 5432:5432
**Image:** postgres:16-alpine

Features:
- PostgreSQL 16 with PostGIS extension
- Persistent storage: `postgres-data` volume
- Automatic initialization from `postgres/init.sql`
- Health checks via `pg_isready`
- Role-based access control
- UUID generation support

**Initialization Script:** `postgres/init.sql`
- Creates traffic schema with all required tables
- Sets up indexes for performance
- Creates materialized views for common queries
- Defines roles: traffic_admin, traffic_user, traffic_readonly

**Database Tables:**
- `users` - User accounts and authentication
- `sessions` - Video processing sessions
- `detections` - Vehicle detections with bounding boxes
- `incidents` - Traffic incidents (collision, congestion, etc.)
- `traffic_flow` - Aggregated traffic metrics
- `alerts` - Notification records
- `analytics` - Custom metrics and performance data

### Redis Cache

**Container:** `traffic-redis`
**Port:** 6379:6379
**Image:** redis:7-alpine

Features:
- In-memory data store for caching
- Persistence enabled (appendonly yes)
- Password-protected access
- Persistent storage: `redis-data` volume
- Health checks via redis-cli

**Usage:**
- Session caching
- Detection result caching
- Rate limiting storage
- Real-time data streaming

### Grafana Dashboards

**Container:** `traffic-grafana`
**Port:** 3001:3000
**Image:** grafana/grafana:latest

Features:
- Pre-configured PostgreSQL datasource
- Traffic overview dashboard with 7 panels
- Automatic dashboard provisioning
- Persistent storage: `grafana-data` volume

**Dashboard Panels:**
1. Vehicle count over time (24h)
2. Vehicle type distribution (pie chart)
3. Incidents by severity (bar chart)
4. Detection confidence histogram
5. Active sessions table
6. Traffic flow heatmap
7. Average speed gauge

**Configuration:**
- Datasource: `grafana/provisioning/datasources/postgres.yml`
- Dashboard provider: `grafana/provisioning/dashboards/traffic.yml`
- Dashboard definition: `grafana/dashboards/traffic-overview.json`

## Docker Compose Configuration

**Main File:** `docker-compose.yml`

### Key Features

1. **Service Dependencies**
   - Backend depends on PostgreSQL and Redis
   - Frontend depends on Backend
   - Grafana depends on PostgreSQL
   - All use health checks

2. **Networks**
   - `traffic-net`: Bridge network for service communication

3. **Volumes**
   - `postgres-data`: Database persistence
   - `redis-data`: Cache persistence
   - `grafana-data`: Dashboard persistence
   - `uploads`: User-uploaded files
   - `models`: YOLO models and trained weights

4. **Environment Configuration**
   - Loaded from `.env` file
   - Database credentials
   - LLM provider settings
   - API configuration
   - Feature flags

### Development Override

**File:** `docker-compose.dev.yml`

Extends production compose with:
- Volume mounts for hot reload
- Debug logging
- Additional services:
  - `redis-commander` (port 8081) - Redis GUI
  - `pgadmin` (port 5050) - PostgreSQL GUI
  - `backend-watch` - File watcher for Python changes

## Configuration

### Environment Variables

**Source:** `.env` (copy from `.env.example`)

Key variables:
- `DB_USER`, `DB_PASSWORD`, `DB_NAME` - Database access
- `REDIS_PASSWORD` - Cache authentication
- `LLM_PROVIDER` - "openai" or "ollama"
- `OPENAI_API_KEY` - OpenAI API key (if using OpenAI)
- `YOLO_MODEL_PATH` - Path to YOLOv8 model
- `DETECTION_CONFIDENCE` - Confidence threshold (0.0-1.0)
- `CORS_ORIGINS` - Allowed origins for CORS
- `UPLOAD_MAX_SIZE` - Maximum file upload size (bytes)
- `GRAFANA_ADMIN_PASSWORD` - Grafana admin password
- `ENVIRONMENT` - "development", "staging", or "production"
- `LOG_LEVEL` - "DEBUG", "INFO", "WARNING", "ERROR"

## Docker Images

### Backend Image

**File:** `Dockerfile.backend`

```dockerfile
FROM python:3.11-slim (base)
  ├─ Install system dependencies
  └─ User: appuser (UID 1000)
      ├─ Python dependencies from requirements.txt
      ├─ Health check: GET /health
      └─ Expose: 8000
```

**Build Context:** Entire project directory
**Build Args:** None (uses env vars at runtime)

### Frontend Image

**File:** `Dockerfile.frontend`

```dockerfile
Stage 1: Build (node:20-alpine)
  └─ npm ci && npm run build → dist/

Stage 2: Serve (nginx:alpine)
  ├─ Copy dist from Stage 1
  ├─ Copy nginx.conf
  ├─ Health check: GET /
  └─ Expose: 80
```

**Build Context:** Entire project directory
**Output:** `/usr/share/nginx/html/`

## Storage

### Persistent Volumes

1. **postgres-data**
   - Location: `/var/lib/postgresql/data`
   - Purpose: Database files
   - Backup: Regular PostgreSQL dumps recommended

2. **redis-data**
   - Location: `/data`
   - Purpose: Redis persistence
   - Format: RDB snapshots + AOF logs

3. **grafana-data**
   - Location: `/var/lib/grafana`
   - Purpose: Dashboards and configurations

4. **uploads**
   - Location: `/app/uploads` (in backend)
   - Purpose: User-uploaded video files
   - Max size: Configurable via UPLOAD_MAX_SIZE

5. **models**
   - Location: `/app/models`
   - Purpose: YOLO and ML models

## Networking

### Traffic-net Bridge Network

All services communicate via `traffic-net`:
- **Backend ↔ Database:** `postgresql://postgres:5432`
- **Backend ↔ Cache:** `redis://redis:6379`
- **Frontend ↔ Backend:** `http://backend:8000`
- **Grafana ↔ Database:** `postgresql://postgres:5432`

### Port Mapping

| Service | Internal | External | Purpose |
|---------|----------|----------|---------|
| Frontend | 80 | 3000 | React SPA |
| Backend | 8000 | 8000 | FastAPI |
| PostgreSQL | 5432 | 5432 | Database |
| Redis | 6379 | 6379 | Cache |
| Grafana | 3000 | 3001 | Dashboards |
| Redis Commander | 8081 | 8081 | (dev only) |
| pgAdmin | 80 | 5050 | (dev only) |

## Health Checks

All services have health checks:

```yaml
Backend:     curl http://localhost:8000/health
Frontend:    wget http://localhost/
PostgreSQL:  pg_isready -U user -d dbname
Redis:       redis-cli ping
Grafana:     curl http://localhost:3000/api/health
```

**Intervals:**
- Check every 30s
- Timeout: 10s
- Retries: 3
- Start period: 40s (backend), 10s (others)

## Code Quality & CI/CD

### Linting & Formatting

**Python:**
- `ruff` - Fast Python linter
- `black` - Code formatter

**JavaScript:**
- `eslint` - JavaScript linter
- `prettier` - Code formatter

### Testing

**Backend:**
- `pytest` with async support
- Coverage reporting
- Integration tests with real database

**Frontend:**
- `vitest` unit tests
- `@testing-library/react` for component testing
- Coverage reports

### CI Pipeline

**File:** `.github/workflows/ci.yml`

Jobs:
1. **lint** - Python (ruff) + JavaScript (eslint)
2. **test-backend** - pytest with PostgreSQL service
3. **test-frontend** - vitest
4. **build-docker** - Build both images (no push)
5. **security-scan** - Trivy vulnerability scanning

Triggers:
- Push to main/develop
- Pull requests to main/develop

## Make Commands

```bash
make help              # Show all available commands
make dev              # Start development environment
make up               # Start production environment
make down             # Stop all services
make lint             # Lint Python + JavaScript
make test             # Run all tests
make docker-build     # Build Docker images
make db-reset         # Reset database (⚠️ destructive)
make health-check     # Check all service health
```

## Monitoring & Observability

### Metrics
- Prometheus-compatible metrics on backend
- Grafana dashboards for visualization
- Custom metrics in `analytics` table

### Logging
- Structured logging with `structlog`
- Log levels: DEBUG, INFO, WARNING, ERROR
- Exportable via syslog/rsyslog

### Tracing
- Request tracking via X-Request-ID headers
- Async operation tracing
- Performance profiling hooks

## Security Considerations

### Image Security
- Non-root user in backend (appuser:1000)
- Minimal base images (python:3.11-slim, nginx:alpine)
- Regular dependency updates

### Network Security
- Services isolated in traffic-net bridge
- No external service exposure except ports
- Environment variables for secrets (never hardcoded)

### Database Security
- Role-based access control
- Password-protected access
- Connections via postgresql:// (not TCP for local)

### API Security
- CORS properly configured
- Rate limiting on all endpoints
- Security headers on frontend
- HTTPS-ready (configure reverse proxy)

## Disaster Recovery

### Backup Strategy
1. **Database:** Regular PostgreSQL dumps
2. **Cache:** Redis persistence (RDB/AOF)
3. **Files:** Regular uploads directory backups
4. **Models:** Version control or artifact storage

### Recovery
1. Stop services: `docker-compose down`
2. Restore volumes from backup
3. Restart: `docker-compose up -d`

## Performance Tuning

### Database
- Indexes on frequently queried columns
- Connection pooling (SQLAlchemy)
- Query optimization in views

### Cache
- Redis for session data
- Frontend asset caching (1-year expiry)
- Gzip compression on all text

### API
- Connection keep-alive
- Request buffering disabled for streaming
- Async/await for all I/O operations

## Troubleshooting

### Service Won't Start
```bash
docker-compose logs <service>
docker-compose exec <service> /bin/sh
```

### Database Issues
```bash
docker-compose exec postgres psql -U traffic_admin -d traffic_intelligence
```

### Redis Issues
```bash
docker-compose exec redis redis-cli
```

### Frontend Build Issues
```bash
docker-compose exec frontend npm install
docker-compose exec frontend npm run build
```

## Future Enhancements

- [ ] Kubernetes manifest files
- [ ] Helm charts for K8s deployment
- [ ] Database replication setup
- [ ] Distributed caching (Redis cluster)
- [ ] Multi-region deployment
- [ ] Auto-scaling configuration
- [ ] Advanced monitoring (DataDog, New Relic)
- [ ] HTTPS/TLS termination
