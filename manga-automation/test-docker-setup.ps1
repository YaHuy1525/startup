# Test script for Docker setup validation (PowerShell)

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Docker Setup Test Script" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

function Print-Status {
    param([bool]$Success, [string]$Message)
    if ($Success) {
        Write-Host "[OK] $Message" -ForegroundColor Green
    } else {
        Write-Host "[FAIL] $Message" -ForegroundColor Red
    }
}

function Print-Info {
    param([string]$Message)
    Write-Host "[INFO] $Message" -ForegroundColor Yellow
}

# Step 1: Validate docker-compose.yml
Write-Host "Step 1: Validating docker-compose.yml" -ForegroundColor White
Write-Host "--------------------------------------" -ForegroundColor White
try {
    docker compose config --quiet
    Print-Status $true "docker-compose.yml is valid"
} catch {
    Print-Status $false "docker-compose.yml has errors"
    exit 1
}
Write-Host ""

# Step 2: Check required files
Write-Host "Step 2: Checking required files" -ForegroundColor White
Write-Host "--------------------------------------" -ForegroundColor White
$files = @(
    "docker-compose.yml",
    "Dockerfile",
    "Dockerfile.python",
    "database/schema.sql",
    "database/migrations/003_queue_system_and_templates.sql",
    "mastra-agents/package.json",
    "remotion-renderer/package.json"
)

foreach ($file in $files) {
    if (Test-Path $file) {
        Print-Status $true "$file exists"
    } else {
        Print-Status $false "$file is missing"
    }
}
Write-Host ""

# Step 3: Check environment variables
Write-Host "Step 3: Checking environment variables" -ForegroundColor White
Write-Host "--------------------------------------" -ForegroundColor White
if (Test-Path ".env") {
    Print-Status $true ".env file exists"
    
    $envContent = Get-Content .env -Raw
    $requiredVars = @("DB_PASSWORD", "ANTHROPIC_API_KEY", "N8N_PASSWORD")
    foreach ($var in $requiredVars) {
        if ($envContent -match "^$var=") {
            Print-Status $true "$var is set"
        } else {
            Print-Status $false "$var is missing"
        }
    }
} else {
    Print-Status $false ".env file is missing"
    Print-Info "Copy .env.example to .env and configure it"
}
Write-Host ""

# Step 4: Build Docker images
Write-Host "Step 4: Building Docker images" -ForegroundColor White
Write-Host "--------------------------------------" -ForegroundColor White
Print-Info "Building manga-agents image..."
try {
    docker compose build --no-cache manga-agents 2>&1 | Select-Object -Last 5
    Print-Status $true "manga-agents image built successfully"
} catch {
    Print-Status $false "Failed to build manga-agents image"
    exit 1
}
Write-Host ""

# Step 5: Start services
Write-Host "Step 5: Starting services" -ForegroundColor White
Write-Host "--------------------------------------" -ForegroundColor White
Print-Info "Starting postgres and redis..."
docker compose up -d postgres redis

Print-Info "Waiting for postgres to be healthy..."
$timeout = 60
$elapsed = 0
$healthy = $false

while ($elapsed -lt $timeout) {
    $status = docker compose ps postgres | Select-String "healthy"
    if ($status) {
        Print-Status $true "Postgres is healthy"
        $healthy = $true
        break
    }
    Start-Sleep -Seconds 2
    $elapsed += 2
}

if (-not $healthy) {
    Print-Status $false "Postgres failed to become healthy"
    docker compose logs postgres
    exit 1
}
Write-Host ""

# Step 6: Apply database migrations
Write-Host "Step 6: Applying database migrations" -ForegroundColor White
Write-Host "--------------------------------------" -ForegroundColor White
Print-Info "Applying migration 003..."
try {
    docker compose exec -T postgres psql -U manga_user -d manga_automation -f /docker-entrypoint-initdb.d/migrations/003_queue_system_and_templates.sql | Out-Null
    Print-Status $true "Migration applied successfully"
} catch {
    Print-Status $false "Failed to apply migration"
    docker compose logs postgres
}
Write-Host ""

# Step 7: Verify database schema
Write-Host "Step 7: Verifying database schema" -ForegroundColor White
Write-Host "--------------------------------------" -ForegroundColor White
$tables = @(
    "chapter_posting_queue",
    "hashtags",
    "caption_templates",
    "video_templates",
    "video_performance"
)

foreach ($table in $tables) {
    $result = docker compose exec -T postgres psql -U manga_user -d manga_automation -c "\dt $table" | Select-String $table
    if ($result) {
        Print-Status $true "Table $table exists"
    } else {
        Print-Status $false "Table $table is missing"
    }
}
Write-Host ""

# Step 8: Start all services
Write-Host "Step 8: Starting all services" -ForegroundColor White
Write-Host "--------------------------------------" -ForegroundColor White
Print-Info "Starting all services..."
docker compose up -d

Print-Info "Waiting for services to be ready..."
Start-Sleep -Seconds 10
Write-Host ""

# Step 9: Check service health
Write-Host "Step 9: Checking service health" -ForegroundColor White
Write-Host "--------------------------------------" -ForegroundColor White
$services = @("postgres", "redis", "manga-agents")

foreach ($service in $services) {
    $status = docker compose ps $service | Select-String "Up"
    if ($status) {
        Print-Status $true "$service is running"
    } else {
        Print-Status $false "$service is not running"
        docker compose logs --tail=20 $service
    }
}
Write-Host ""

# Step 10: Test API endpoints
Write-Host "Step 10: Testing API endpoints" -ForegroundColor White
Write-Host "--------------------------------------" -ForegroundColor White
Print-Info "Testing manga-agents health endpoint..."
try {
    $response = Invoke-WebRequest -Uri "http://localhost:3001/health" -UseBasicParsing -TimeoutSec 5
    if ($response.Content -match "ok") {
        Print-Status $true "manga-agents API is responding"
    } else {
        Print-Status $false "manga-agents API is not responding correctly"
    }
} catch {
    Print-Status $false "manga-agents API is not responding"
    docker compose logs --tail=20 manga-agents
}
Write-Host ""

# Summary
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Test Summary" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""
Print-Info "Docker setup test completed!"
Print-Info "Check the output above for any failures."
Write-Host ""
Print-Info "Next steps:"
Write-Host "  1. Import N8N workflows from n8n-workflows/ directory"
Write-Host "  2. Configure N8N credentials"
Write-Host "  3. Test the queue system with:"
Write-Host "     Invoke-WebRequest -Uri 'http://localhost:3001/pipeline/populate-queue' -Method POST -ContentType 'application/json' -Body '{\"manga_id\": 1}'"
Write-Host ""
