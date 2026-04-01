.PHONY: help build up down logs clean lint test coverage docker-build docker-push

# Variables
DOCKER_REGISTRY ?= localhost:5000
IMAGE_NAME_BACKEND ?= traffic-intelligence-backend
IMAGE_NAME_FRONTEND ?= traffic-intelligence-frontend
IMAGE_TAG ?= latest

help:
	@echo "Multimodal Traffic Intelligence Platform - Available Commands"
	@echo "============================================================="
	@echo ""
	@echo "Development:"
	@echo "  make dev              - Start development environment"
	@echo "  make up               - Start all services with docker-compose"
	@echo "  make down             - Stop all services"
	@echo "  make logs             - View docker logs"
	@echo "  make clean            - Remove all containers, volumes, and cache"
	@echo ""
	@echo "Code Quality:"
	@echo "  make lint             - Run linting checks (Python + JavaScript)"
	@echo "  make format           - Auto-format code (Python + JavaScript)"
	@echo "  make test             - Run all tests (backend + frontend)"
	@echo "  make test-backend     - Run backend tests only"
	@echo "  make test-frontend    - Run frontend tests only"
	@echo "  make coverage         - Generate coverage reports"
	@echo ""
	@echo "Docker:"
	@echo "  make docker-build     - Build Docker images"
	@echo "  make docker-push      - Push Docker images to registry"
	@echo ""
	@echo "Database:"
	@echo "  make db-reset         - Reset database (⚠️  WARNING: destructive)"
	@echo "  make db-migrate       - Run database migrations"
	@echo ""

dev:
	@echo "Starting development environment..."
	docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d
	@echo "Development environment started. Access:"
	@echo "  Frontend: http://localhost:3000"
	@echo "  Backend API: http://localhost:8000"
	@echo "  Grafana: http://localhost:3001"

up:
	docker-compose up -d

down:
	docker-compose down

logs:
	docker-compose logs -f

logs-backend:
	docker-compose logs -f backend

logs-frontend:
	docker-compose logs -f frontend

clean:
	docker-compose down -v
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache
	rm -rf htmlcov
	rm -rf coverage.xml
	rm -rf node_modules
	rm -rf dist
	@echo "Cleaned up containers, volumes, and cache files"

lint:
	@echo "Linting Python code with ruff..."
	ruff check backend/
	@echo "Linting JavaScript code with eslint..."
	npm run lint
	@echo "All linting checks passed!"

format:
	@echo "Formatting Python code with black and ruff..."
	black backend/
	ruff check backend/ --fix
	@echo "Formatting JavaScript code with eslint..."
	npm run lint:fix
	@echo "All formatting completed!"

test:
	@echo "Running all tests..."
	$(MAKE) test-backend
	$(MAKE) test-frontend

test-backend:
	@echo "Running backend tests..."
	pytest backend/tests/ -v --cov=backend --cov-report=html

test-frontend:
	@echo "Running frontend tests..."
	npm run test:unit

coverage: test
	@echo "Coverage reports generated"
	@echo "Backend: htmlcov/index.html"
	@echo "Frontend: coverage/index.html"

docker-build:
	@echo "Building Docker images..."
	docker build -f Dockerfile.backend -t $(DOCKER_REGISTRY)/$(IMAGE_NAME_BACKEND):$(IMAGE_TAG) .
	docker build -f Dockerfile.frontend -t $(DOCKER_REGISTRY)/$(IMAGE_NAME_FRONTEND):$(IMAGE_TAG) .
	@echo "Docker images built successfully!"

docker-push:
	@echo "Pushing Docker images to registry..."
	docker push $(DOCKER_REGISTRY)/$(IMAGE_NAME_BACKEND):$(IMAGE_TAG)
	docker push $(DOCKER_REGISTRY)/$(IMAGE_NAME_FRONTEND):$(IMAGE_TAG)
	@echo "Docker images pushed successfully!"

db-reset:
	@echo "⚠️  WARNING: This will delete all database data!"
	@read -p "Are you sure? (yes/no) " -n 3 -r; \
	if [ $$REPLY = "yes" ]; then \
		docker-compose exec postgres psql -U $${DB_USER} -d $${DB_NAME} -c "DROP SCHEMA traffic CASCADE;"; \
		docker-compose restart postgres; \
		echo "Database reset completed"; \
	else \
		echo "Database reset cancelled"; \
	fi

db-migrate:
	@echo "Running database migrations..."
	docker-compose exec backend alembic upgrade head
	@echo "Migrations completed!"

install-deps:
	@echo "Installing Python dependencies..."
	pip install -r requirements.txt
	@echo "Installing Node dependencies..."
	npm install
	@echo "All dependencies installed!"

health-check:
	@echo "Checking service health..."
	@echo "Backend: $$(curl -s http://localhost:8000/health || echo 'Unhealthy')"
	@echo "Frontend: $$(curl -s http://localhost/health || echo 'Unhealthy')"
	@echo "Grafana: $$(curl -s http://localhost:3001/api/health || echo 'Unhealthy')"
	@echo "PostgreSQL: $$(docker-compose exec -T postgres pg_isready -U $${DB_USER} || echo 'Unhealthy')"
	@echo "Redis: $$(docker-compose exec -T redis redis-cli ping || echo 'Unhealthy')"
