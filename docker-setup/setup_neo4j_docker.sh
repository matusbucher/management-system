#!/bin/bash
# Automated Neo4j Docker Setup Script for Linux/macOS
#
# Run this once Docker is fully running:
#     bash docker-setup/setup_neo4j_docker.sh
#
# This will:
# 1. Check Docker is running
# 2. Create Neo4j container with persistent storage
# 3. Wait for container to be healthy
# 4. Test the connection

set -e

# Configuration
PORT="${1:-7687}"
WEB_PORT="${2:-7474}"
PASSWORD="${3:-password}"
FORCE="${4:-false}"

# Colors for output (can be overridden by setting NO_COLOR=1)
if [ -z "$NO_COLOR" ]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    BLUE='\033[0;34m'
    NC='\033[0m' # No Color
else
    RED=''
    GREEN=''
    YELLOW=''
    BLUE=''
    NC=''
fi

print_header() {
    echo ""
    echo "======================================================================"
    echo "$1"
    echo "======================================================================"
    echo ""
}

print_ok() {
    echo -e "${GREEN}[OK]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_wait() {
    echo -e "${BLUE}[WAIT]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_header "NEO4J DOCKER SETUP"

# Step 1: Check Docker
echo "Step 1: Checking Docker..."
if ! command -v docker &> /dev/null; then
    print_error "Docker not found. Please install Docker first."
    echo "   Linux: https://docs.docker.com/engine/install/"
    echo "   macOS: https://docs.docker.com/desktop/install/mac-install/"
    echo ""
    exit 1
fi

DOCKER_VERSION=$(docker --version)
print_ok "Docker found: $DOCKER_VERSION"
echo ""

# Step 2: Check Docker daemon
echo "Step 2: Checking Docker daemon..."
DOCKER_READY=false
for i in {1..12}; do
    if docker ps &> /dev/null; then
        print_ok "Docker daemon is running"
        echo ""
        DOCKER_READY=true
        break
    fi
    echo "  Waiting... ($i/12)"
    sleep 5
done

if [ "$DOCKER_READY" = false ]; then
    print_error "Docker daemon not responding. Please start Docker and try again."
    echo "   1. Start Docker Desktop"
    echo "   2. Wait 2-3 minutes for startup"
    echo "   3. Run this script again"
    echo ""
    exit 1
fi

# Step 3: Check existing container
echo "Step 3: Checking for existing container..."
CONTAINER_ID=$(docker ps -a --filter "name=eurlex-neo4j" --quiet 2>/dev/null || true)

if [ -n "$CONTAINER_ID" ]; then
    echo "Found existing container: $CONTAINER_ID"
    if [ "$FORCE" = "true" ] || [ "$FORCE" = "--force" ]; then
        echo "Removing existing container (--force flag)..."
        docker rm -f eurlex-neo4j > /dev/null
        print_ok "Removed"
        echo ""
    else
        print_ok "Container already exists"
        echo ""
        echo "Checking if it's running..."
        RUNNING=$(docker ps --filter "name=eurlex-neo4j" --quiet 2>/dev/null || true)
        if [ -n "$RUNNING" ]; then
            print_ok "Container is already running"
            echo ""
            docker ps --filter "name=eurlex-neo4j"
            echo ""
            echo "Skipping creation..."
            goto_test_connection=true
        else
            print_wait "Container exists but stopped. Starting it..."
            docker start eurlex-neo4j > /dev/null
            sleep 5
            goto_test_connection=true
        fi
    fi
fi

if [ "$goto_test_connection" != "true" ]; then
    # Step 4: Create container
    echo "Step 4: Creating Neo4j container..."
    echo "  Name: eurlex-neo4j"
    echo "  Bolt Port: $PORT"
    echo "  Web Port: $WEB_PORT"
    echo "  Storage: Persistent volume 'eurlex-data'"
    echo "  Auth: neo4j / $PASSWORD"
    echo ""

    docker run -d \
        --name eurlex-neo4j \
        --publish "${PORT}:7687" \
        --publish "${WEB_PORT}:7474" \
        --env NEO4J_AUTH="neo4j/${PASSWORD}" \
        --env NEO4J_server_jvm_additional="-Xmx4g" \
        --volume eurlex-data:/data \
        neo4j:latest > /dev/null

    if [ $? -eq 0 ]; then
        print_ok "Container created"
        echo ""
    else
        print_error "Failed to create container"
        echo ""
        exit 1
    fi

    # Step 5: Wait for Neo4j to be ready
    echo "Step 5: Waiting for Neo4j to be ready..."
    READY=false
    for i in {1..30}; do
        if docker logs eurlex-neo4j 2>/dev/null | grep -q "Started"; then
            print_ok "Neo4j is ready"
            echo ""
            READY=true
            break
        fi
        echo "  Waiting... ($i/30 seconds)"
        sleep 1
    done

    if [ "$READY" = false ]; then
        print_warning "Neo4j startup taking longer than expected"
        echo "   But container should be ready soon. Proceeding with tests..."
        echo ""
    fi
fi

# Step 6: Test connection
echo "Step 6: Testing connection..."
echo "  Connecting to bolt://localhost:${PORT}..."
echo ""

python3 << EOF
import sys
from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable

try:
    driver = GraphDatabase.driver(
        'bolt://localhost:$PORT',
        auth=('neo4j', '$PASSWORD'),
        connection_acquire_timeout=10
    )
    with driver.session() as session:
        result = session.run('MATCH (n) RETURN COUNT(n) as count')
        count = result.single()[0]
    driver.close()
    
    print(f"[OK] Connection successful!")
    print(f"   Nodes: {count}")
    print(f"   Web UI: http://localhost:$WEB_PORT")
    
except ServiceUnavailable:
    print("[ERROR] Neo4j not responding yet. It may still be starting.")
    print("   Try connecting in 10-15 seconds.")
    sys.exit(1)
except Exception as e:
    print(f"[ERROR] Error: {e}")
    sys.exit(1)
EOF

if [ $? -eq 0 ]; then
    echo ""
    print_ok "SETUP COMPLETE!"
    echo ""
    echo "Database Details:"
    echo "  Connection String: bolt://localhost:${PORT}"
    echo "  Username: neo4j"
    echo "  Password: $PASSWORD"
    echo "  Web UI: http://localhost:${WEB_PORT}"
    echo "  Storage: Persistent (eurlex-data volume)"
    echo ""
    echo "Useful Docker commands:"
    echo "  docker logs eurlex-neo4j          # View logs"
    echo "  docker stop eurlex-neo4j          # Stop database"
    echo "  docker start eurlex-neo4j         # Start database"
    echo "  docker rm eurlex-neo4j            # Delete container"
    echo "  docker volume rm eurlex-data      # Delete data"
    echo ""
    echo "Next steps:"
    echo "  1. Run verification: python test/verify_neo4j.py"
    echo "  2. Run module tests: python test/test_modules.py"
    echo ""
else
    echo ""
    print_warning "Connection test failed. Neo4j may still be starting."
    echo "Verify with: python test/verify_neo4j.py"
    echo "Or check Docker logs: docker logs eurlex-neo4j"
    echo ""
fi
