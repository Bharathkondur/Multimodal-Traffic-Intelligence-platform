#!/bin/bash

################################################################################
# Quick Demo Launcher
#
# Starts the platform in demo mode with simulated data:
# - No real video needed
# - API simulator provides fake traffic data
# - Dashboard shows live analytics on simulated events
#
# Usage: chmod +x run_demo.sh && ./run_demo.sh
################################################################################

set -e

# Color codes
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

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

print_info() {
    echo -e "${BLUE}ℹ${NC}  $1"
}

################################################################################
# Step 1: Check Prerequisites
################################################################################

check_requirements() {
    print_header "Checking Requirements"

    if ! command -v docker-compose &> /dev/null; then
        print_error "docker-compose not found"
        echo "Install Docker Desktop or docker-compose: https://docs.docker.com/compose/install/"
        exit 1
    fi
    print_success "docker-compose found"

    if ! command -v curl &> /dev/null; then
        print_error "curl not found (required for health checks)"
        exit 1
    fi
    print_success "curl found"
}

################################################################################
# Step 2: Ensure .env is Set Up
################################################################################

setup_env() {
    print_header "Configuring Environment"

    if [ ! -f "$SCRIPT_DIR/.env" ]; then
        if [ ! -f "$SCRIPT_DIR/.env.example" ]; then
            print_error ".env.example not found"
            exit 1
        fi

        print_info "Creating .env from template..."
        cp "$SCRIPT_DIR/.env.example" "$SCRIPT_DIR/.env"

        # Generate random passwords
        DB_PASSWORD=$(openssl rand -base64 12)
        REDIS_PASSWORD=$(openssl rand -base64 12)
        GRAFANA_PASSWORD=$(openssl rand -base64 12)

        # Update with defaults
        sed -i.bak "s/DB_PASSWORD=.*/DB_PASSWORD=$DB_PASSWORD/" "$SCRIPT_DIR/.env"
        sed -i.bak "s/REDIS_PASSWORD=.*/REDIS_PASSWORD=$REDIS_PASSWORD/" "$SCRIPT_DIR/.env"
        sed -i.bak "s/GRAFANA_ADMIN_PASSWORD=.*/GRAFANA_ADMIN_PASSWORD=$GRAFANA_PASSWORD/" "$SCRIPT_DIR/.env"
        sed -i.bak "s/DEMO_MODE=.*/DEMO_MODE=true/" "$SCRIPT_DIR/.env"
        sed -i.bak "s/ENVIRONMENT=.*/ENVIRONMENT=development/" "$SCRIPT_DIR/.env"

        rm -f "$SCRIPT_DIR/.env.bak"

        print_success "Created .env with demo mode enabled"
    else
        # Ensure demo mode is enabled
        if grep -q "DEMO_MODE=false" "$SCRIPT_DIR/.env"; then
            print_info "Enabling demo mode in .env..."
            sed -i.bak "s/DEMO_MODE=.*/DEMO_MODE=true/" "$SCRIPT_DIR/.env"
            rm -f "$SCRIPT_DIR/.env.bak"
            print_success "Demo mode enabled"
        else
            print_success ".env already configured for demo"
        fi
    fi
}

################################################################################
# Step 3: Start Docker Services
################################################################################

start_services() {
    print_header "Starting Services"

    cd "$SCRIPT_DIR"

    print_info "Starting containers (postgres, redis, backend, frontend, grafana)..."
    docker-compose up -d

    if [ $? -ne 0 ]; then
        print_error "Failed to start containers"
        exit 1
    fi

    print_success "Containers started"
}

################################################################################
# Step 4: Wait for Services
################################################################################

wait_for_services() {
    print_header "Waiting for Services"

    local max_attempts=60
    local attempt=0

    print_info "Waiting for backend to respond..."

    while [ $attempt -lt $max_attempts ]; do
        attempt=$((attempt + 1))

        if curl -s http://localhost:8000/health > /dev/null 2>&1; then
            print_success "Backend is ready!"
            break
        fi

        echo -n "."
        sleep 1

        if [ $attempt -eq $max_attempts ]; then
            print_error "Backend did not respond (timeout)"
            print_info "Check logs: docker-compose logs backend"
            exit 1
        fi
    done

    echo

    print_info "Waiting for frontend..."
    attempt=0

    while [ $attempt -lt $max_attempts ]; do
        attempt=$((attempt + 1))

        if curl -s http://localhost:3000 > /dev/null 2>&1; then
            print_success "Frontend is ready!"
            break
        fi

        echo -n "."
        sleep 1
    done

    echo
}

################################################################################
# Step 5: Start Simulator
################################################################################

start_simulator() {
    print_header "Starting Simulator"

    print_info "Initializing demo data stream..."

    # Give the backend time to fully initialize
    sleep 2

    # Call the simulator API endpoint
    RESPONSE=$(curl -s -X POST http://localhost:8000/api/v1/simulator/start \
        -H "Content-Type: application/json" \
        -d '{"num_objects": 5, "speed": "medium"}' 2>/dev/null || echo "")

    if [ -z "$RESPONSE" ]; then
        print_info "Simulator endpoint may not be available in your setup"
        print_info "Dashboard will show empty state"
    else
        print_success "Simulator started - generating demo data"
    fi
}

################################################################################
# Step 6: Open Browser
################################################################################

open_dashboard() {
    print_header "Opening Dashboard"

    local dashboard_url="http://localhost:3000"

    print_info "Opening dashboard: $dashboard_url"

    # Try to open browser based on OS
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        if command -v xdg-open &> /dev/null; then
            xdg-open "$dashboard_url" 2>/dev/null || true
        elif command -v sensible-browser &> /dev/null; then
            sensible-browser "$dashboard_url" 2>/dev/null || true
        else
            print_info "Please open: $dashboard_url"
        fi
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        open "$dashboard_url" 2>/dev/null || true
    elif [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" ]]; then
        start "$dashboard_url" 2>/dev/null || true
    else
        print_info "Please open: $dashboard_url"
    fi
}

################################################################################
# Step 7: Print Summary
################################################################################

print_summary() {
    print_header "Demo Ready!"

    echo -e "${GREEN}✓ Platform is running in DEMO MODE${NC}\n"

    echo "Access points:"
    echo "  ${BLUE}Dashboard:${NC}        http://localhost:3000"
    echo "  ${BLUE}Grafana:${NC}          http://localhost:3001"
    echo "  ${BLUE}API Docs:${NC}         http://localhost:8000/docs"
    echo "  ${BLUE}Health Check:${NC}     http://localhost:8000/health"
    echo

    echo "Grafana login:"
    echo "  ${BLUE}User:${NC}             admin"
    GRAFANA_PASS=$(grep "GRAFANA_ADMIN_PASSWORD=" "$SCRIPT_DIR/.env" | cut -d '=' -f2)
    echo "  ${BLUE}Password:${NC}         $GRAFANA_PASS"
    echo

    echo "Demo Features:"
    echo "  • Simulated traffic stream"
    echo "  • Real-time object detection visualization"
    echo "  • Live analytics dashboard"
    echo "  • Grafana metrics and monitoring"
    echo

    echo "Useful Commands:"
    echo "  ${BLUE}View logs:${NC}        docker-compose logs -f backend"
    echo "  ${BLUE}Stop demo:${NC}        docker-compose down"
    echo "  ${BLUE}Restart:${NC}          docker-compose restart"
    echo "  ${BLUE}Full reset:${NC}       docker-compose down -v"
    echo

    echo "Next Steps:"
    echo "  1. Open the dashboard at http://localhost:3000"
    echo "  2. Explore the live analytics"
    echo "  3. Check Grafana at http://localhost:3001"
    echo "  4. Try the API at http://localhost:8000/docs"
    echo "  5. Configure real API key in .env to enable AI features"
    echo
}

################################################################################
# Main Execution
################################################################################

main() {
    echo -e "${BLUE}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║                      DEMO MODE LAUNCHER                       ║"
    echo "║           Multimodal Traffic Intelligence Platform            ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"

    check_requirements
    setup_env
    start_services
    wait_for_services
    start_simulator
    open_dashboard
    print_summary

    echo -e "${YELLOW}Press Ctrl+C to stop the demo${NC}"
    echo

    # Keep running
    docker-compose logs -f backend &
    wait
}

# Run main function
main "$@"
