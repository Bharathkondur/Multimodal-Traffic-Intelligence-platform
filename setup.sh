#!/bin/bash

################################################################################
# Multimodal Traffic Intelligence Platform - One Command Setup
#
# This script automates the entire setup process including:
# - Prerequisite checks (Docker, docker-compose)
# - Environment configuration
# - API key setup (Gemini)
# - Model downloads
# - Docker image builds and container startup
#
# Usage: chmod +x setup.sh && ./setup.sh
################################################################################

set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script variables
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
ENV_FILE="$SCRIPT_DIR/.env"
ENV_EXAMPLE="$SCRIPT_DIR/.env.example"
MODELS_DIR="$SCRIPT_DIR/backend/models"
DEMO_MODE=false

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

    local missing_deps=()

    # Check Docker
    if ! check_command docker; then
        missing_deps+=("docker")
        print_error "Docker not found"
        echo -e "\n${YELLOW}Install Docker:${NC}"
        echo "  macOS/Windows: https://www.docker.com/products/docker-desktop"
        echo "  Linux: https://docs.docker.com/engine/install/"
    else
        DOCKER_VERSION=$(docker --version)
        print_success "$DOCKER_VERSION"
    fi

    # Check docker-compose
    if ! check_command docker-compose; then
        missing_deps+=("docker-compose")
        print_error "docker-compose not found"
        echo -e "\n${YELLOW}Install docker-compose:${NC}"
        echo "  Usually included with Docker Desktop"
        echo "  Or: pip install docker-compose"
    else
        DC_VERSION=$(docker-compose --version)
        print_success "$DC_VERSION"
    fi

    # Check curl (for health checks)
    if ! check_command curl; then
        print_warning "curl not found (optional, used for health checks)"
    else
        print_success "curl found"
    fi

    if [ ${#missing_deps[@]} -gt 0 ]; then
        print_error "Missing critical dependencies: ${missing_deps[*]}"
        echo -e "\n${RED}Please install the missing dependencies and try again.${NC}"
        exit 1
    fi

    print_success "All prerequisites installed"
}

################################################################################
# Step 2: Create .env Configuration
################################################################################

create_env_config() {
    print_header "Step 2: Environment Configuration"

    if [ -f "$ENV_FILE" ]; then
        print_warning ".env file already exists"
        read -p "Overwrite existing .env? (y/N) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            print_info "Keeping existing .env configuration"
            return
        fi
    fi

    if [ ! -f "$ENV_EXAMPLE" ]; then
        print_error ".env.example not found at $ENV_EXAMPLE"
        exit 1
    fi

    # Copy template
    cp "$ENV_EXAMPLE" "$ENV_FILE"
    print_success "Created .env from template"

    # Generate random passwords
    DB_PASSWORD=$(openssl rand -base64 12)
    REDIS_PASSWORD=$(openssl rand -base64 12)
    GRAFANA_PASSWORD=$(openssl rand -base64 12)
    JWT_SECRET=$(openssl rand -base64 32)

    # Update .env with secure defaults
    sed -i.bak "s/DB_PASSWORD=.*/DB_PASSWORD=$DB_PASSWORD/" "$ENV_FILE"
    sed -i.bak "s/REDIS_PASSWORD=.*/REDIS_PASSWORD=$REDIS_PASSWORD/" "$ENV_FILE"
    sed -i.bak "s/GRAFANA_ADMIN_PASSWORD=.*/GRAFANA_ADMIN_PASSWORD=$GRAFANA_PASSWORD/" "$ENV_FILE"
    sed -i.bak "s/JWT_SECRET=.*/JWT_SECRET=$JWT_SECRET/" "$ENV_FILE"
    sed -i.bak "s/ENVIRONMENT=.*/ENVIRONMENT=production/" "$ENV_FILE"
    sed -i.bak "s/DEMO_MODE=.*/DEMO_MODE=false/" "$ENV_FILE"

    rm -f "$ENV_FILE.bak"

    print_success "Generated secure passwords and updated .env"
}

################################################################################
# Step 3: Configure API Keys
################################################################################

configure_api_keys() {
    print_header "Step 3: API Key Configuration"

    echo "This platform supports multiple LLM providers:"
    echo "  1. ${GREEN}Gemini 2.0 Flash${NC} (Recommended - FREE 1,500 req/day)"
    echo "  2. OpenAI (Paid)"
    echo "  3. Ollama (Local - no internet needed)"
    echo "  4. Skip for now - use demo mode"
    echo

    read -p "Choose option (1-4, default 4): " -n 1 -r
    echo
    choice=${REPLY:-4}

    case $choice in
        1)
            echo -e "\n${BLUE}Gemini Setup:${NC}"
            echo "  1. Go to: https://aistudio.google.com/apikey"
            echo "  2. Sign in with Google account"
            echo "  3. Click 'Create API key'"
            echo "  4. Copy the key"
            echo
            read -p "Paste your Gemini API key (or press Enter to skip): " -r api_key
            if [ -n "$api_key" ]; then
                sed -i.bak "s|GOOGLE_API_KEY=.*|GOOGLE_API_KEY=$api_key|" "$ENV_FILE"
                sed -i.bak "s/LLM_PROVIDER=.*/LLM_PROVIDER=gemini/" "$ENV_FILE"
                rm -f "$ENV_FILE.bak"
                print_success "Gemini API key configured"
            else
                print_warning "Gemini API key not provided - will use demo mode"
                DEMO_MODE=true
            fi
            ;;
        2)
            read -p "Paste your OpenAI API key (or press Enter to skip): " -r api_key
            if [ -n "$api_key" ]; then
                sed -i.bak "s|OPENAI_API_KEY=.*|OPENAI_API_KEY=$api_key|" "$ENV_FILE"
                sed -i.bak "s/LLM_PROVIDER=.*/LLM_PROVIDER=openai/" "$ENV_FILE"
                rm -f "$ENV_FILE.bak"
                print_success "OpenAI API key configured"
            else
                print_warning "OpenAI API key not provided - will use demo mode"
                DEMO_MODE=true
            fi
            ;;
        3)
            echo "Ollama requires running locally:"
            echo "  1. Install Ollama: https://ollama.ai"
            echo "  2. Run: ollama pull llama2"
            echo "  3. Run: ollama serve"
            echo
            read -p "Is Ollama running on http://localhost:11434? (y/N) " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                sed -i.bak "s/LLM_PROVIDER=.*/LLM_PROVIDER=ollama/" "$ENV_FILE"
                rm -f "$ENV_FILE.bak"
                print_success "Ollama configured"
            else
                print_warning "Ollama not detected - will use demo mode"
                DEMO_MODE=true
            fi
            ;;
        *)
            print_info "Demo mode enabled (no LLM integration)"
            DEMO_MODE=true
            ;;
    esac

    if [ "$DEMO_MODE" = true ]; then
        sed -i.bak "s/DEMO_MODE=.*/DEMO_MODE=true/" "$ENV_FILE"
        rm -f "$ENV_FILE.bak"
    fi
}

################################################################################
# Step 4: Download Models
################################################################################

download_models() {
    print_header "Step 4: Model Download"

    mkdir -p "$MODELS_DIR"

    if [ -f "$MODELS_DIR/yolov8n.pt" ]; then
        print_warning "YOLOv8 model already exists"
        read -p "Re-download? (y/N) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            print_success "Using existing model"
            return
        fi
    fi

    print_info "Downloading YOLOv8n model (83 MB)..."
    print_info "This may take 1-2 minutes depending on connection"

    # Use Python to download YOLOv8 model
    python3 << 'EOF'
import sys
try:
    from ultralytics import YOLO
    print("Downloading YOLOv8n model...")
    model = YOLO('yolov8n.pt')
    print("✓ Model downloaded successfully")
except Exception as e:
    print(f"✗ Failed to download model: {e}", file=sys.stderr)
    sys.exit(1)
EOF

    if [ $? -eq 0 ]; then
        print_success "YOLOv8 model ready"
    else
        print_warning "Could not auto-download model"
        print_info "Model will be downloaded on first run inside Docker"
    fi
}

################################################################################
# Step 5: Build Docker Images
################################################################################

build_docker_images() {
    print_header "Step 5: Building Docker Images"

    cd "$SCRIPT_DIR"

    print_info "This may take 5-15 minutes on first build..."
    print_info "Building backend image..."

    docker-compose build backend
    if [ $? -ne 0 ]; then
        print_error "Failed to build backend image"
        exit 1
    fi
    print_success "Backend image built"

    print_info "Building frontend image..."
    docker-compose build frontend
    if [ $? -ne 0 ]; then
        print_error "Failed to build frontend image"
        exit 1
    fi
    print_success "Frontend image built"

    print_success "All Docker images built successfully"
}

################################################################################
# Step 6: Start Services
################################################################################

start_services() {
    print_header "Step 6: Starting Services"

    cd "$SCRIPT_DIR"

    print_info "Starting containers..."
    docker-compose up -d

    if [ $? -ne 0 ]; then
        print_error "Failed to start containers"
        print_info "View logs: docker-compose logs -f"
        exit 1
    fi

    print_success "Containers started"
}

################################################################################
# Step 7: Wait for Health Checks
################################################################################

wait_for_services() {
    print_header "Step 7: Waiting for Services"

    local max_attempts=30
    local attempt=0

    print_info "Waiting for services to become healthy..."
    echo "  (This typically takes 20-30 seconds)"
    echo

    while [ $attempt -lt $max_attempts ]; do
        attempt=$((attempt + 1))

        # Check backend health
        if docker-compose ps backend | grep -q "(healthy)"; then
            print_success "Backend is healthy"
        else
            echo -n "."
        fi

        # Check postgres health
        if docker-compose ps postgres | grep -q "(healthy)"; then
            print_success "Database is healthy"
        fi

        # Check frontend health
        if docker-compose ps frontend | grep -q "(healthy)"; then
            print_success "Frontend is healthy"
            break
        fi

        if [ $attempt -eq $max_attempts ]; then
            print_warning "Health check timeout"
            print_info "Services may still be initializing"
            print_info "Check status: docker-compose ps"
            print_info "View logs: docker-compose logs -f backend"
            break
        fi

        sleep 2
    done

    echo
}

################################################################################
# Step 8: Print URLs and Instructions
################################################################################

print_summary() {
    print_header "Setup Complete!"

    echo -e "${GREEN}✓ Platform is ready to use!${NC}\n"

    echo "Access your platform:"
    echo "  ${BLUE}Dashboard:${NC}      http://localhost:3000"
    echo "  ${BLUE}Grafana:${NC}        http://localhost:3001 (user: admin)"
    echo "  ${BLUE}API Docs:${NC}       http://localhost:8000/docs"
    echo

    echo "Default credentials:"
    echo "  ${BLUE}Grafana password:${NC} (check .env GRAFANA_ADMIN_PASSWORD)"
    echo

    if [ "$DEMO_MODE" = true ]; then
        echo -e "${YELLOW}Demo Mode Enabled:${NC}"
        echo "  - Platform runs with simulated data"
        echo "  - AI features use local processing only"
        echo "  - Add API key later: edit .env and restart"
        echo
    fi

    echo "Useful commands:"
    echo "  ${BLUE}View logs:${NC}           docker-compose logs -f backend"
    echo "  ${BLUE}Stop services:${NC}       docker-compose down"
    echo "  ${BLUE}Restart services:${NC}    docker-compose restart"
    echo "  ${BLUE}Clean everything:${NC}    docker-compose down -v"
    echo
    echo "Documentation:"
    echo "  ${BLUE}README:${NC}              cat README.md"
    echo "  ${BLUE}Quickstart:${NC}          cat QUICKSTART.md"
    echo "  ${BLUE}API Reference:${NC}       http://localhost:8000/docs"
    echo
}

################################################################################
# Main Execution
################################################################################

main() {
    echo -e "${BLUE}"
    echo "████████╗██████╗  █████╗ ███████╗███████╗██╗ ██████╗ "
    echo "╚══██╔══╝██╔══██╗██╔══██╗██╔════╝██╔════╝██║██╔════╝ "
    echo "   ██║   ██████╔╝███████║███████╗█████╗  ██║██║  ███╗"
    echo "   ██║   ██╔══██╗██╔══██║╚════██║██╔══╝  ██║██║   ██║"
    echo "   ██║   ██║  ██║██║  ██║███████║███████╗██║╚██████╔╝"
    echo "   ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝╚══════╝╚═╝ ╚═════╝ "
    echo -e "${NC}"
    echo "Multimodal Traffic Intelligence Platform Setup"
    echo "=================================================="
    echo

    check_prerequisites
    create_env_config
    configure_api_keys
    download_models
    build_docker_images
    start_services
    wait_for_services
    print_summary
}

# Run main function
main
