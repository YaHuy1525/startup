#!/bin/bash
# Script to apply database migrations
# Usage: ./apply_migration.sh <migration_file>

set -e

# Load environment variables
if [ -f ../.env ]; then
    export $(cat ../.env | grep -v '^#' | xargs)
fi

# Default values
DB_HOST=${DB_HOST:-localhost}
DB_PORT=${DB_PORT:-5434}
DB_NAME=${DB_NAME:-manga_automation}
DB_USER=${DB_USER:-manga_user}

if [ -z "$1" ]; then
    echo "Usage: $0 <migration_file>"
    echo "Example: $0 003_queue_system_and_templates.sql"
    exit 1
fi

MIGRATION_FILE="$1"

if [ ! -f "$MIGRATION_FILE" ]; then
    echo "Error: Migration file '$MIGRATION_FILE' not found"
    exit 1
fi

echo "Applying migration: $MIGRATION_FILE"
echo "Database: $DB_NAME on $DB_HOST:$DB_PORT"
echo ""

# Apply migration using docker compose exec if postgres container is running
if docker compose -f ../docker-compose.yml ps postgres | grep -q "Up"; then
    echo "Using docker compose exec..."
    docker compose -f ../docker-compose.yml exec -T postgres psql -U "$DB_USER" -d "$DB_NAME" < "$MIGRATION_FILE"
else
    # Try direct connection
    echo "Using direct psql connection..."
    PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -f "$MIGRATION_FILE"
fi

echo ""
echo "✓ Migration applied successfully!"
