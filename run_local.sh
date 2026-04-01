#!/bin/bash

################################################################################
# Local Development Mode
#
# Run backend and frontend locally without Docker:
# - Direct Python/Node processes for faster iteration
# - Requires: Python 3.11+, Node 18+, PostgreSQL, Redis
# - Perfect for development and debugging
#
# Usage: chmod +x run_local.sh && ./run_local.sh
################################################################################

set -e

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"
VENV_DIR="$BACKEND_DIR/venv"

################################################################################
# Helper Functions
################################################################################

print_header() {
    echo -e "\n${BLUE}╔════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║${NC}  $1"
    echo -e "${BLUE}╚════════════════════════════════════════════════════════════════╝${NC}\n"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC}  $1"
}

print_info() {
    echo -e "${BLUE}ℹ${NC}  $1"
}

check_command() {
    if ! command -v "$1" &> /dev/null; then
        return 1
    fi
    return 0
}

################################################################################
# Step 1: Check Prerequisites
################################################################################

check_prerequisites() {
    print_header "Step 1: Checking Prerequisites"

    local missing=()

    # Python 3.11+
    if ! check_command python3; then
        missing+=("python3")
        print_error "Python 3 not found"
    else
        PY_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2)
        print_success "Python $PY_VERSION"
    fi

    # Node 18+
    if ! check_command node; then
        missing+=("node")
        print_error "Node.js not found"
    else
        NODE_VERSION=$(node --version)
        print_success "Node $NODE_VERSION"
    fi

    # PostgreSQL
    if ! check_command psql; then
        print_warning "PostgreSQL client not found"
        print_info "PostgreSQL must be running (local or remote)"
        echo "  Install: https://www.postgresql.org/download/"
    else
        print_success "PostgreSQL client found"
    fi

    # Redis
    if ! check_command redis-cli; then
        print_warning "Redis client not found"
        print_info "Redis must be running (local or remote)"
        echo "  Install: https://redis.io/download"
    else
        print_success "Redis client found"
    fi

    # Git (optional)
    if ! check_command git; then
        print_warning "Git not found (optional)"
    else
        print_success "Git found"
    fi

    if [ ${#missing[@]} -gt 0 ]; then
        print_error "Missing critical dependencies: ${missing[*]}"
        exit 1
    fi

    print_success "All prerequisites satisfied"
}

################################################################################
# Step 2: Setup Python Virtual Environment
################################################################################

setup_python_env() {
    print_header "Step 2: Python Environment Setup"

    if [ ! -d "$VENV_DIR" ]; then
        print_info "Creating Python virtual environment..."
        python3 -m venv "$VENV_DIR"
        print_success "Virtual environment created"
    else
        print_info "Virtual environment already exists"
    fi

    # Activate venv
    source "$VENV_DIR/bin/activate"
    print_success "Virtual environment activated"

    print_info "Installing Python dependencies..."
    pip install --upgrade pip setuptools wheel > /dev/null
    pip install -r "$BACKEND_DIR/requirements.txt"

    if [ $? -eq 0 ]; then
        print_success "Python dependencies installed"
    else
        print_error "Failed to install dependencies"
        exit 1
    fi
}

################################################################################
# Step 3: Check PostgreSQL
################################################################################

check_postgres() {
    print_header "Step 3: PostgreSQL Check"

    # Try to connect to postgres
    DB_HOST=${DB_HOST:-localhost}
    DB_USER=${DB_USER:-traffic_admin}
    DB_PASSWORD=${DB_PASSWORD:-}
    DB_NAME=${DB_NAME:-traffic_intelligence}

    if [ -z "$DB_PASSWORD" ]; then
        # Try without password
        if PGPASSWORD="" psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -c "SELECT 1" > /dev/null 2>&1; then
            print_success "PostgreSQL is running and accessible"
            return 0
        fi
    else
        if PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -c "SELECT 1" > /dev/null 2>&1; then
            print_success "PostgreSQL is running and accessible"
            return 0
        fi
    fi

    print_error "Cannot connect to PostgreSQL"
    echo
    echo "Setup PostgreSQL:"
    echo "  1. Install PostgreSQL: https://www.postgresql.org/download/"
    echo "  2. Start the service"
    echo "  3. Create user: createuser traffic_admin"
    echo "  4. Create database: createdb traffic_intelligence"
    echo "  5. Run setup.sh or update .env with correct credentials"
    echo

    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
}

################################################################################
# Step 4: Check Redis
################################################################################

check_redis() {
    print_header "Step 4: Redis Check"

    REDIS_HOST=${REDIS_HOST:-localhost}
    REDIS_PORT=${REDIS_PORT:-6379}

    if redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" ping > /dev/null 2>&1; then
        print_success "Redis is running and accessible"
        return 0
    fi

    print_error "Cannot connect to Redis"
    echo
    echo "Setup Redis:"
    echo "  macOS: brew install redis && brew services start redis"
    echo "  Linux: sudo apt-get install redis-server && sudo systemctl start redis-server"
    echo "  Windows: https://github.com/microsoftarchive/redis/releases"
    echo

    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
}

################################################################################
# Step 5: Setup Environment
################################################################################

setup_environment() {
    print_header "Step 5: Environment Configuration"

    if [ ! -f "$SCRIPT_DIR/.env" ]; then
        if [ ! -f "$SCRIPT_DIR/.env.example" ]; then
            print_error ".env.example not found"
            exit 1
        fi

        print_info "Creating .env file..."
        cp "$SCRIPT_DIR/.env.example" "$SCRIPT_DIR/.env"

        # Set development defaults
        sed -i.bak "s/ENVIRONMENT=.*/ENVIRONMENT=development/" "$SCRIPT_DIR/.env"
        sed -i.bak "s/LOG_LEVEL=.*/LOG_LEVEL=DEBUG/" "$SCRIPT_DIR/.env"
        sed -i.bak "s/DEBUG=.*/DEBUG=True/" "$SCRIPT_DIR/.env"

        rm -f "$SCRIPT_DIR/.env.bak"

        print_success "Created .env with development settings"
    else
        print_info ".env file already exists"
    fi

    # Export env variables
    set -a
    source "$SCRIPT_DIR/.env"
    set +a

    print_success "Environment loaded"
}

################################################################################
# Step 6: Download Models
################################################################################

download_models() {
    print_header "Step 6: Model Downloads"

    MODELS_DIR="$BACKEND_DIR/models"
    mkdir -p "$MODELS_DIR"

    if [ -f "$MODELS_DIR/yolov8n.pt" ]; then
        print_success "YOLOv8 model already exists"
        return
    fi

    print_info "Downloading YOLOv8n model (83 MB)..."
    print_info "This may take 1-2 minutes..."

    python3 << 'EOF'
import sys
try:
    from ultralytics import YOLO
    print("Downloading YOLOv8n model...")
    model = YOLO('yolov8n.pt')
    print("✓ Model downloaded successfully")
except Exception as e:
    print(f"✗ Failed: {e}", file=sys.stderr)
    sys.exit(1)
EOF

    if [ $? -eq 0 ]; then
        print_success "YOLOv8 model ready"
    else
        print_warning "Could not download model - will retry on startup"
    fi
}

################################################################################
# Step 7: Database Migrations
################################################################################

run_migrations() {
    print_header "Step 7: Database Migrations"

    cd "$BACKEND_DIR"
    source "$VENV_DIR/bin/activate"

    if [ -d "alembic" ]; then
        print_info "Running Alembic migrations..."
        alembic upgrade head

        if [ $? -eq 0 ]; then
            print_success "Database migrations completed"
        else
            print_warning "Migration had issues - continuing anyway"
        fi
    else
        print_info "No Alembic migrations found - using existing schema"
    fi
}

################################################################################
# Step 8: Start Backend
################################################################################

start_backend() {
    print_header "Step 8: Starting Backend"

    cd "$BACKEND_DIR"
    source "$VENV_DIR/bin/activate"

    print_info "Starting FastAPI server on http://localhost:8000"
    print_info "Press Ctrl+C to stop"
    echo

    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 &
    BACKEND_PID=$!

    echo $BACKEND_PID > "$SCRIPT_DIR/.backend.pid"
    print_success "Backend started (PID: $BACKEND_PID)"
}

################################################################################
# Step 9: Setup Frontend
################################################################################

setup_frontend() {
    print_header "Step 9: Frontend Setup"

    if [ ! -d "$FRONTEND_DIR" ]; then
        print_error "Frontend directory not found"
        exit 1
    fi

    cd "$FRONTEND_DIR"

    if [ ! -d "node_modules" ]; then
        print_info "Installing Node dependencies..."
        npm install

        if [ $? -ne 0 ]; then
            print_error "Failed to install dependencies"
            exit 1
        fi
        print_success "Node dependencies installed"
    else
        print_info "Node dependencies already installed"
    fi
}

################################################################################
# Step 10: Start Frontend
################################################################################

start_frontend() {
    print_header "Step 10: Starting Frontend"

    cd "$FRONTEND_DIR"

    print_info "Starting development server on http://localhost:3000"
    print_info "Press Ctrl+C to stop"
    echo

    npm run dev &
    FRONTEND_PID=$!

    echo $FRONTEND_PID > "$SCRIPT_DIR/.frontend.pid"
    print_success "Frontend started (PID: $FRONTEND_PID)"
}

################################################################################
# Cleanup on Exit
################################################################################

cleanup() {
    print_header "Shutting Down"

    if [ -f "$SCRIPT_DIR/.backend.pid" ]; then
        BACKEND_PID=$(cat "$SCRIPT_DIR/.backend.pid")
        kill $BACKEND_PID 2>/dev/null || true
        rm -f "$SCRIPT_DIR/.backend.pid"
        print_success "Backend stopped"
    fi

    if [ -f "$SCRIPT_DIR/.frontend.pid" ]; then
        FRONTEND_PID=$(cat "$SCRIPT_DIR/.frontend.pid")
        kill $FRONTEND_PID 2>/dev/null || true
        rm -f "$SCRIPT_DIR/.frontend.pid"
        print_success "Frontend stopped"
    fi

    print_success "Cleanup complete"
}

trap cleanup EXIT

################################################################################
# Print Summary
################################################################################

print_summary() {
    print_header "Local Development Running!"

    echo -e "${GREEN}✓ All services started${NC}\n"

    echo "Access points:"
    echo "  ${BLUE}Dashboard:${NC}  http://localhost:3000"
    echo "  ${BLUE}API:${NC}         http://localhost:8000"
    echo "  ${BLUE}API Docs:${NC}    http://localhost:8000/docs"
    echo
    echo "Logs:"
    echo "  ${BLUE}Backend:${NC}     tail -f logs/backend.log"
    echo "  ${BLUE}Frontend:${NC}    npm logs in another terminal"
    echo
    echo "Both services have hot-reload enabled:"
    echo "  • Backend: Restart on Python file changes"
    echo "  • Frontend: Restart on React file changes"
    echo
    echo "Press Ctrl+C to stop all services"
    echo
}

################################################################################
# Main Execution
################################################################################

main() {
    echo -e "${BLUE}"
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║          LOCAL DEVELOPMENT MODE - NO DOCKER REQUIRED           ║"
    echo "║           Multimodal Traffic Intelligence Platform             ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"

    check_prerequisites
    setup_python_env
    check_postgres
    check_redis
    setup_environment
    download_models
    run_migrations
    setup_frontend
    start_backend
    start_frontend
    print_summary

    # Wait indefinitely
    wait
}

# Run main
main "$@"
