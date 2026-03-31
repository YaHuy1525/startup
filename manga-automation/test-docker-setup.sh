#!/bin/bash
# Test script for Docker setup validation

set -e

echo "=========================================="
echo "Docker Setup Test Script"
echo "=========================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print status
print_status() {
    if [ $1 -eq 0 ]; then
        echo -e "${GREEN}✓${NC} $2"
    else
        echo -e "${RED}✗${NC} $2"
    fi
}

# Function to print info
print_info() {
    echo -e "${YELLOW}ℹ${NC} $1"
}

echo "Step 1: Validating docker-compose.yml"
echo "--------------------------------------"
if docker compose config --quiet; then
    print_status 0 "docker-compose.yml is valid"
else
    print_status 1 "docker-compose.yml has errors"
    exit 1
fi
echo ""

echo "Step 2: Checking required files"
echo "--------------------------------------"
files=(
    "docker-compose.yml"
    "Dockerfile"
    "Dockerfile.python"
    "database/schema.sql"
    "database/migrations/003_queue_system_and_templates.sql"
    "mastra-agents/package.json"
    "remotion-renderer/package.json"
)

for file in "${files[@]}"; do
    if [ -f "$file" ]; then
        print_status 0 "$file exists"
    else
        print_status 1 "$file is missing"
    fi
done
echo ""

echo "Step 3: Checking environment variables"
echo "--------------------------------------"
if [ -f ".env" ]; then
    print_status 0 ".env file exists"
    
    # Check for required variables
    required_vars=("DB_PASSWORD" "ANTHROPIC_API_KEY" "N8N_PASSWORD")
    for var in "${required_vars[@]}"; do
        if grep -q "^${var}=" .env; then
            print_status 0 "$var is set"
        else
            print_status 1 "$var is missing"
        fi
    done
else
    print_status 1 ".env file is missing"
    print_info "Copy .env.example to .env and configure it"
fi
echo ""

echo "Step 4: Building Docker images"
echo "--------------------------------------"
print_info "Building manga-agents image..."
if docker compose build --no-cache manga-agents 2>&1 | tail -5; then
    print_status 0 "manga-agents image built successfully"
else
    print_status 1 "Failed to build manga-agents image"
    exit 1
fi
echo ""

echo "Step 5: Starting services"
echo "--------------------------------------"
print_info "Starting postgres and redis..."
docker compose up -d postgres redis

print_info "Waiting for postgres to be healthy..."
timeout=60
elapsed=0
while [ $elapsed -lt $timeout ]; do
    if docker compose ps postgres | grep -q "healthy"; then
        print_status 0 "Postgres is healthy"
        break
    fi
    sleep 2
    elapsed=$((elapsed + 2))
done

if [ $elapsed -ge $timeout ]; then
    print_status 1 "Postgres failed to become healthy"
    docker compose logs postgres
    exit 1
fi
echo ""

echo "Step 6: Applying database migrations"
echo "--------------------------------------"
print_info "Applying migration 003..."
if docker compose exec -T postgres psql -U manga_user -d manga_automation -f /docker-entrypoint-initdb.d/migrations/003_queue_system_and_templates.sql > /dev/null 2>&1; then
    print_status 0 "Migration applied successfully"
else
    print_status 1 "Failed to apply migration"
    docker compose logs postgres
fi
echo ""

echo "Step 7: Verifying database schema"
echo "--------------------------------------"
tables=(
    "chapter_posting_queue"
    "hashtags"
    "caption_templates"
    "video_templates"
    "video_performance"
)

for table in "${tables[@]}"; do
    if docker compose exec -T postgres psql -U manga_user -d manga_automation -c "\dt $table" | grep -q "$table"; then
        print_status 0 "Table $table exists"
    else
        print_status 1 "Table $table is missing"
    fi
done
echo ""

echo "Step 8: Starting all services"
echo "--------------------------------------"
print_info "Starting all services..."
docker compose up -d

print_info "Waiting for services to be ready..."
sleep 10
echo ""

echo "Step 9: Checking service health"
echo "--------------------------------------"
services=("postgres" "redis" "manga-agents")

for service in "${services[@]}"; do
    if docker compose ps $service | grep -q "Up"; then
        print_status 0 "$service is running"
    else
        print_status 1 "$service is not running"
        docker compose logs --tail=20 $service
    fi
done
echo ""

echo "Step 10: Testing API endpoints"
echo "--------------------------------------"
print_info "Testing manga-agents health endpoint..."
if curl -s http://localhost:3001/health | grep -q "ok"; then
    print_status 0 "manga-agents API is responding"
else
    print_status 1 "manga-agents API is not responding"
    docker compose logs --tail=20 manga-agents
fi
echo ""

echo "=========================================="
echo "Test Summary"
echo "=========================================="
echo ""
print_info "Docker setup test completed!"
print_info "Check the output above for any failures."
echo ""
print_info "Next steps:"
echo "  1. Import N8N workflows from n8n-workflows/ directory"
echo "  2. Configure N8N credentials"
echo "  3. Test the queue system with: curl -X POST http://localhost:3001/pipeline/populate-queue -H 'Content-Type: application/json' -d '{\"manga_id\": 1}'"
echo ""
