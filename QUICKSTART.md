# Quick Start Guide

Get the Multimodal Traffic Intelligence Platform up and running in minutes.

## Prerequisites

- Docker & Docker Compose (version 3.9+)
- Make (optional, for convenient commands)
- 4GB RAM minimum (8GB+ recommended)
- 10GB disk space for data volumes

## 1. Clone and Setup

```bash
cd /path/to/project
cp .env.example .env
```

Edit `.env` to customize:
```bash
# Essential settings
DB_PASSWORD=your_secure_password
REDIS_PASSWORD=your_redis_password
GRAFANA_ADMIN_PASSWORD=your_grafana_password
OPENAI_API_KEY=sk-your-key-here  # Or use Ollama

# Development
ENVIRONMENT=development
LOG_LEVEL=DEBUG
```

## 2. Start Services

### Option A: Using Make
```bash
make dev
```

### Option B: Using Docker Compose
```bash
# Production-like environment
docker-compose up -d

# Development with hot-reload
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d
```

## 3. Access Applications

| Service | URL | Credentials |
|---------|-----|-------------|
| Frontend | http://localhost:3000 | N/A |
| Backend API | http://localhost:8000 | N/A |
| Grafana | http://localhost:3001 | admin / (from .env) |
| pgAdmin | http://localhost:5050 | admin@traffic.local / admin |
| Redis Commander | http://localhost:8081 | N/A |

## 4. Verify Health

```bash
# All in one
make health-check

# Or individually
curl http://localhost:8000/health
curl http://localhost/health
docker-compose exec postgres pg_isready -U traffic_admin
docker-compose exec redis redis-cli ping
```

## 5. Common Tasks

### View Logs
```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f backend
docker-compose logs -f frontend
```

### Database Operations
```bash
# Connect to database
docker-compose exec postgres psql -U traffic_admin -d traffic_intelligence

# View tables
\dt traffic.*

# Exit
\q
```

### Redis Operations
```bash
# Connect to Redis CLI
docker-compose exec redis redis-cli

# View keys
KEYS *

# Exit
EXIT
```

### Run Tests
```bash
make test              # All tests
make test-backend      # Backend only
make test-frontend     # Frontend only
```

### Code Quality
```bash
make lint              # Check code
make format            # Auto-format code
```

## 6. Development Workflow

### Making Changes

**Backend Changes:**
```bash
# Edit Python files in backend/
# Changes automatically reload (if using dev compose)
docker-compose logs -f backend
```

**Frontend Changes:**
```bash
# Edit React files in frontend/src/
# Changes automatically hot-reload
docker-compose logs -f frontend
```

**Database Schema Changes:**
```bash
# Edit postgres/init.sql
# Reset database
make db-reset
docker-compose up -d postgres
```

### Adding Dependencies

**Python:**
```bash
# Edit requirements.txt
pip install -r requirements.txt
docker-compose rebuild backend
docker-compose up -d backend
```

**JavaScript:**
```bash
# Edit package.json
npm install
docker-compose rebuild frontend
docker-compose up -d frontend
```

## 7. Deployment Checklist

Before deploying to production:

- [ ] Copy `.env.example` to `.env`
- [ ] Set strong passwords in `.env`
- [ ] Set `ENVIRONMENT=production`
- [ ] Set `LOG_LEVEL=INFO` or higher
- [ ] Review and configure CORS_ORIGINS
- [ ] Set proper UPLOAD_MAX_SIZE
- [ ] Configure SMTP for alerts (optional)
- [ ] Set up SSL/TLS reverse proxy
- [ ] Configure PostgreSQL backups
- [ ] Test database failover
- [ ] Set up monitoring/alerting
- [ ] Review security settings
- [ ] Performance test the platform

## 8. Troubleshooting

### Services won't start
```bash
# Check Docker daemon
docker ps

# Remove all containers/volumes and start fresh
docker-compose down -v
docker-compose up -d

# Check logs
docker-compose logs
```

### Database connection errors
```bash
# Verify PostgreSQL is running
docker-compose ps postgres

# Test connection
docker-compose exec postgres psql -U traffic_admin -d traffic_intelligence -c "SELECT 1"
```

### Out of disk space
```bash
# Clean up Docker
docker system prune
docker volume prune

# Check volume usage
docker exec traffic-postgres du -sh /var/lib/postgresql/data
```

### Frontend build errors
```bash
# Clear cache and rebuild
docker-compose exec frontend npm cache clean --force
docker-compose rebuild frontend
```

### Backend crashes
```bash
# Check logs for errors
docker-compose logs backend

# Verify dependencies
docker-compose exec backend pip check

# Test import
docker-compose exec backend python -c "from app.main import app; print('OK')"
```

## 9. Next Steps

1. **Configure API integrations**
   - OpenAI API key
   - YOLO model path
   - Camera feed URLs

2. **Customize dashboards**
   - Edit Grafana dashboards
   - Add custom metrics
   - Set up alerts

3. **Integrate with systems**
   - Connect to traffic cameras
   - Set up incident notifications
   - Configure data export

4. **Scale the platform**
   - Add more backend workers
   - Configure load balancing
   - Set up database replication

## 10. Getting Help

- **Documentation:** See `INFRASTRUCTURE.md` for detailed setup
- **Logs:** `docker-compose logs -f`
- **Database:** Connect via pgAdmin (localhost:5050)
- **Cache:** View via Redis Commander (localhost:8081)
- **Code:** Check `/backend` and `/frontend` directories

## Advanced: Production Deployment

### Using Docker Stack (Swarm)
```bash
docker stack deploy -c docker-compose.yml traffic
```

### Using Kubernetes (future)
```bash
kubectl apply -f k8s/
```

### Environment-Specific Configs
```bash
# Production
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Staging
docker-compose -f docker-compose.yml -f docker-compose.staging.yml up -d
```

## Security Reminders

- Keep `.env` file secure (never commit to git)
- Use strong, unique passwords
- Enable authentication on all services
- Set up SSL/TLS for production
- Configure firewalls properly
- Regular security updates
- Monitor and audit access logs

## Performance Tips

1. Allocate adequate RAM (8GB+ for production)
2. Use SSD storage for database
3. Configure connection pooling
4. Enable Redis caching
5. Compress API responses (enabled by default)
6. Use CDN for static assets
7. Monitor and tune queries

## Support

For issues, bugs, or feature requests:
1. Check `INFRASTRUCTURE.md` for detailed docs
2. Review logs: `docker-compose logs`
3. Consult troubleshooting section above
4. Create an issue with logs and reproduction steps

---

**Happy analyzing traffic data! 🚦📊**
