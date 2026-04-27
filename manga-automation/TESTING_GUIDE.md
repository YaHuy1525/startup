# Docker Build and Test Guide

This guide covers a clean local validation run for the `manga-automation` stack.

## 1) Prerequisites

- Docker Desktop running
- Ports available: `3000`, `3001`, `5434`, `5679`, `6380`, `8001`, `8080`
- `.env` populated from `.env.example`

## 2) Build Images

From `manga-automation`:

```powershell
docker compose build
```

Expected result:
- Build completes with exit code `0`
- Images are created for `manga-agents`, `python-worker`, `telegram-bot`, `research-scheduler`, `dashboard`

## 3) Start Services

```powershell
docker compose up -d
```

Check running containers:

```powershell
docker compose ps
```

Healthy/Up services should include:
- `postgres`
- `redis`
- `chromadb`
- `manga-agents`
- `python-worker`
- `n8n`
- `dashboard`

## 4) Core Health Checks

```powershell
curl.exe -sS http://localhost:3001/health
curl.exe -sS http://localhost:8080/health
```

Expected responses:
- `{"status":"ok","service":"manga-agents",...}`
- `{"status":"ok","service":"python-worker"}`

## 5) Apply DB Migrations (Required for Monetization APIs)

If you are testing KPI/monetization endpoints, apply migration `009`:

```powershell
docker compose exec -T postgres psql -U manga_user -d manga_automation -f /docker-entrypoint-initdb.d/migrations/009_monetization_control_plane.sql
```

Expected output includes:
- `CREATE TABLE` entries
- `INSERT 0 9` (KPI seeds)
- `INSERT 0 6` (channel config seeds)

## 6) Monetization API Smoke Tests

Use PowerShell JSON serialization to avoid CLI escaping issues:

```powershell
$empty = @{} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "http://localhost:8080/monetization/weekly-plan" -ContentType "application/json" -Body $empty | ConvertTo-Json -Depth 6
Invoke-RestMethod -Method Post -Uri "http://localhost:8080/monetization/offer-matrix" -ContentType "application/json" -Body $empty | ConvertTo-Json -Depth 6

$kpi = @{ days = 7; write_alerts = $false } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "http://localhost:8080/monetization/kpi/evaluate" -ContentType "application/json" -Body $kpi | ConvertTo-Json -Depth 6
```

Expected:
- `weekly-plan`: returns `weekly_schedule` and `high_cpm_field_rotation`
- `offer-matrix`: returns CTA mapping by content type
- `kpi/evaluate`: returns `window_days`, `platform_status`, and `alerts`

## 7) Optional Workflow Validation (n8n)

- Open: `http://localhost:5679`
- Verify workflows are imported and active:
  - `06_arbitrage_pipeline.json`
  - `10_balanced_multiplatform_schedule.json`
  - `11_monetization_weekly_optimization.json`
- Run a manual execution and confirm no node failures.

## 8) Logs and Troubleshooting

View service logs:

```powershell
docker compose logs -f manga-agents
docker compose logs -f python-worker
docker compose logs -f postgres
```

Common issues:

- `relation "... does not exist"`  
  Run migration `009_monetization_control_plane.sql`.

- `invalid JSON body` during curl POST in PowerShell  
  Use `Invoke-RestMethod` with `ConvertTo-Json` instead of raw `curl -d`.

- Service unhealthy or not starting  
  Check `.env` values (`DB_PASSWORD`, API keys) and run:
  ```powershell
  docker compose down
  docker compose up -d
  ```

## 9) Stop Stack

```powershell
docker compose down
```

