# Setup & Run Infrastructure Guide

This guide covers the three ways to run the **Multimodal Traffic Intelligence Platform**:

1. **setup.sh** — Automated one-command setup (Recommended for first-time users)
2. **run_demo.sh** — Quick demo launcher with simulated data
3. **run_local.sh** — Local development mode without Docker

---

## Quick Start (5 minutes)

```bash
# Make setup script executable and run it
chmod +x setup.sh
./setup.sh
```

This will:
- Check Docker and docker-compose prerequisites
- Create `.env` configuration
- Prompt for LLM API key (optional)
- Download YOLOv8 model
- Build Docker images
- Start all services
- Print access URLs

After completion, access the platform:
- **Dashboard**: http://localhost:3000
- **API Docs**: http://localhost:8000/docs
- **Grafana**: http://localhost:3001

---

## Method 1: Automated Setup (setup.sh)

### Prerequisites
- **Docker** (Desktop or Engine): https://www.docker.com/products/docker-desktop
- **docker-compose** (usually included with Docker Desktop)
- **curl** (optional, for health checks)
- **openssl** (usually pre-installed)

### Usage

```bash
chmod +x setup.sh
./setup.sh
```

### What It Does

#### Step 1: Prerequisite Check
- Verifies Docker and docker-compose installation
- Provides install links if missing

#### Step 2: Environment Configuration
- Creates `.env` from `.env.example`
- Generates secure random passwords for:
  - PostgreSQL
  - Redis
  - Grafana
  - JWT tokens

#### Step 3: API Key Configuration
Interactive menu to choose LLM provider:

**Option 1: Gemini** (Recommended - FREE)
- 1,500 free requests/day
- Sign up at https://aistudio.google.com/apikey
- Best for development and demos

**Option 2: OpenAI** (Paid)
- Requires API key: https://platform.openai.com
- Billed per token

**Option 3: Ollama** (Local - No internet)
- Requires local Ollama installation
- Run `ollama pull llama2` first
- Perfect for offline development

**Option 4: Skip** (Demo Mode)
- Platform runs with simulated data only
- Add API key later by editing `.env`

#### Step 4: Model Download
- Downloads YOLOv8n model (83 MB)
- Required for object detection
- Cached for future runs

#### Step 5: Docker Build
- Builds backend image with all modules:
  - Detection (YOLO)
  - Processing (video/stream)
  - Analytics (metrics)
  - Agents (LLM integration)
  - API (FastAPI)
- Builds frontend image (React + Nginx)
- Takes 5-15 minutes on first build

#### Step 6: Start Services
- Launches docker-compose with:
  - Backend API (8000)
  - Frontend (3000)
  - PostgreSQL (5432)
  - Redis (6379)
  - Grafana (3001)

#### Step 7: Health Checks
- Waits up to 30 seconds for services to become healthy
- Checks endpoints and database connectivity

#### Step 8: Print Summary
- Shows access URLs
- Displays default credentials
- Lists useful commands

### Troubleshooting setup.sh

**Docker not found**
```bash
# macOS/Windows: Install Docker Desktop
# https://www.docker.com/products/docker-desktop

# Linux: Install Docker Engine
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
```

**Build fails**
```bash
# View detailed logs
docker-compose logs backend

# Clean and rebuild
docker-compose down
rm -rf backend/models/*.pt
./setup.sh
```

**Services not becoming healthy**
```bash
# Check service status
docker-compose ps

# View logs
docker-compose logs -f backend
```

---

## Method 2: Quick Demo (run_demo.sh)

### Perfect For
- Trying the platform without real video
- Testing the API and dashboard
- Demonstrations and presentations
- Quick feature exploration

### Usage

```bash
chmod +x run_demo.sh
./run_demo.sh
```

### What It Does

1. Checks Docker and curl prerequisites
2. Creates `.env` with demo mode enabled
3. Starts all containers
4. Waits for services to respond
5. Initializes demo data stream via simulator API
6. Opens browser to dashboard

### Demo Features

- **Simulated Traffic Stream**: Fake vehicle data generator
- **Live Dashboard**: Real-time analytics on simulated events
- **API Access**: Full API available for testing
- **Grafana Metrics**: Monitoring with pre-built dashboards
- **No API Key Needed**: Runs completely offline

### Demo Commands

```bash
# Run demo
./run_demo.sh

# View logs while demo is running (in another terminal)
docker-compose logs -f backend

# Stop demo
docker-compose down

# Reset demo completely
docker-compose down -v  # Removes data volumes too
```

### Access Points in Demo

- **Dashboard**: http://localhost:3000
- **Grafana**: http://localhost:3001 (user: admin, pwd: check .env)
- **API Docs**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/health

---

## Method 3: Local Development (run_local.sh)

### Perfect For
- Developers working on backend/frontend code
- Fast iteration with hot reload
- Debugging and testing
- No Docker needed

### Prerequisites

```bash
# Python 3.11+
python3 --version

# Node 18+
node --version

# PostgreSQL (running locally or remote)
# https://www.postgresql.org/download/

# Redis (running locally or remote)
# https://redis.io/download

# Optional: Git
git --version
```

### Setup PostgreSQL

**macOS** (using Homebrew):
```bash
brew install postgresql
brew services start postgresql
createuser traffic_admin
createdb -O traffic_admin traffic_intelligence
```

**Linux** (Debian/Ubuntu):
```bash
sudo apt-get install postgresql postgresql-contrib
sudo systemctl start postgresql
sudo -u postgres createuser traffic_admin
sudo -u postgres createdb -O traffic_admin traffic_intelligence
```

**Windows**:
- Download PostgreSQL installer: https://www.postgresql.org/download/windows/
- Run installer, use password: `traffic_admin`
- During setup, create database: `traffic_intelligence`

### Setup Redis

**macOS**:
```bash
brew install redis
brew services start redis
```

**Linux** (Debian/Ubuntu):
```bash
sudo apt-get install redis-server
sudo systemctl start redis-server
```

**Windows**:
- Download: https://github.com/microsoftarchive/redis/releases
- Extract and run: `redis-server.exe`

### Usage

```bash
chmod +x run_local.sh
./run_local.sh
```

### What It Does

1. Checks Python 3.11+, Node 18+, PostgreSQL, Redis
2. Creates Python virtual environment
3. Installs Python dependencies
4. Checks database connectivity
5. Checks Redis connectivity
6. Creates/loads `.env` configuration
7. Downloads YOLOv8 model
8. Runs database migrations (Alembic)
9. Installs Node dependencies
10. Starts backend server (with hot reload)
11. Starts frontend dev server (with hot reload)

### Access Points in Local Mode

- **Frontend**: http://localhost:3000 (Vite dev server)
- **Backend API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/health

### Hot Reload

Both backend and frontend support hot reload:

```
backend/: Edit Python files → Auto-restart
frontend/: Edit React files → Auto-refresh in browser
```

### Database Migrations

For local development with Alembic:

```bash
# Create a new migration
alembic revision --autogenerate -m "Add new table"

# Apply migrations
alembic upgrade head

# Downgrade one migration
alembic downgrade -1
```

---

## Configuration (.env File)

### Database
```env
DB_USER=traffic_admin              # PostgreSQL user
DB_PASSWORD=secure_password        # PostgreSQL password
DB_NAME=traffic_intelligence       # Database name
DB_HOST=postgres (Docker) or localhost (local)
DB_PORT=5432
```

### Redis
```env
REDIS_PASSWORD=redis_password
REDIS_HOST=redis (Docker) or localhost (local)
REDIS_PORT=6379
```

### LLM Configuration

**Gemini** (FREE - Recommended):
```env
LLM_PROVIDER=gemini
GOOGLE_API_KEY=your-key-here       # https://aistudio.google.com/apikey
GEMINI_MODEL=gemini-2.0-flash      # Latest model
```

**OpenAI** (Paid):
```env
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-your-key-here    # https://platform.openai.com
```

**Ollama** (Local - No Cost):
```env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama2                # Run: ollama pull llama2
```

### YOLO Object Detection
```env
YOLO_MODEL_PATH=/app/models/yolov8n.pt  # Model file path
YOLO_MODEL_SIZE=n                       # n=nano, s=small, m=medium, l=large
DETECTION_CONFIDENCE=0.5                # Confidence threshold (0-1)
DETECTION_IOU_THRESHOLD=0.45            # IoU threshold for NMS
MAX_DETECTIONS_PER_FRAME=100            # Max objects per frame
```

### Application
```env
ENVIRONMENT=development            # development or production
LOG_LEVEL=DEBUG                     # DEBUG, INFO, WARNING, ERROR
DEBUG=True                          # Enable debug mode
DEMO_MODE=false                     # Enable simulated data
```

### Grafana
```env
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=password     # Change in production!
```

---

## Common Tasks

### View Logs

**Docker**:
```bash
# Backend logs
docker-compose logs -f backend

# All services
docker-compose logs -f

# Specific service
docker-compose logs -f postgres
```

**Local**:
```bash
# Backend logs appear in terminal
# Frontend logs appear in second terminal
```

### Restart Services

**Docker**:
```bash
# Restart single service
docker-compose restart backend

# Restart all services
docker-compose restart

# Full reset (removes volumes)
docker-compose down -v
./setup.sh
```

**Local**:
```bash
# Press Ctrl+C to stop
# Run again
./run_local.sh
```

### Reset Everything

```bash
# Docker
docker-compose down -v
rm -rf backend/models/*.pt
./setup.sh

# Local
# Press Ctrl+C
rm -rf backend/venv
./run_local.sh
```

### Access Database

**Docker**:
```bash
docker-compose exec postgres psql -U traffic_admin -d traffic_intelligence
```

**Local**:
```bash
psql -U traffic_admin -d traffic_intelligence
```

SQL queries:
```sql
-- List tables
\dt

-- Check detection results
SELECT * FROM detections LIMIT 10;

-- Check video processes
SELECT * FROM video_processing ORDER BY created_at DESC LIMIT 10;
```

### Monitor Resources

**Docker**:
```bash
# Real-time resource usage
docker stats

# Specific service
docker stats traffic-backend
```

**Local**:
```bash
# System resources
top          # macOS/Linux
Get-Process  # Windows (PowerShell)
```

---

## Troubleshooting

### "Port already in use"

```bash
# Find what's using the port (Linux/macOS)
lsof -i :8000

# Kill the process
kill -9 <PID>

# Or change ports in docker-compose.yml or .env
```

### "Database connection refused"

```bash
# Docker: Check postgres logs
docker-compose logs postgres

# Local: Verify PostgreSQL is running
psql -U postgres -c "SELECT 1"

# Create database if missing
createdb traffic_intelligence
```

### "Redis connection refused"

```bash
# Check Redis is running
redis-cli ping

# If not running:
# macOS: brew services start redis
# Linux: sudo systemctl start redis-server
```

### "ModuleNotFoundError: No module named 'app'"

```bash
# Local mode: Ensure you're in backend directory
cd backend
source venv/bin/activate

# Or run from project root:
export PYTHONPATH=/path/to/backend:$PYTHONPATH
```

### "Frontend not loading"

```bash
# Check Nginx logs (Docker)
docker-compose logs frontend

# Try rebuilding frontend
docker-compose down frontend
docker-compose build frontend
docker-compose up -d frontend
```

---

## Next Steps

1. **Set up LLM API key** (Gemini recommended)
2. **Explore API** at http://localhost:8000/docs
3. **Upload test video** or use simulator
4. **Check Grafana dashboards** at http://localhost:3001
5. **Read main README** for detailed feature documentation

---

## Support

For issues:
1. Check logs: `docker-compose logs -f backend`
2. Verify prerequisites are installed
3. Ensure `.env` has correct credentials
4. Try clean reset: `docker-compose down -v && ./setup.sh`
5. Check README.md for detailed documentation
